"""Deterministic protocol parameter resolution.

This module is executable policy: it converts a run plan and polymer-class rules into
concrete tool arguments. It contains no agent prompts or simulation execution.
"""

from __future__ import annotations

import hashlib
import json
import sys
from functools import lru_cache
from pathlib import Path
from rules_common import load_rules, resolve_ff_family, get_class_entry, resolve_member_value
from hardware_runtime import host_matches, live_host
from mol_python import run_in_mol_env, RDKIT_CLI
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = REPO_ROOT / 'guides' / 'polymer_rules.json'

def load_plan(plan_path: str) -> dict:
    with open(plan_path) as f:
        return json.load(f)

def apply_plan(cls: dict, plan: dict, args) -> dict:
    """Overlay an approved run_plan.json's decided_params onto the class entry.

    The plan carries the scientific agent's decisions (FF, system size, T-schedule,
    property knobs); runtime wiring (paths, gpu_ids, mpi_ranks) stays in CLI args. For a
    class-default scaffold, decided_params is a subset of cls with identical values. For a
    reasoned plan, decided_params may differ and those values take effect here.

    Also backfills --smiles and --properties from the plan when not given on the CLI, so
    the plan artifact is a self-contained source of truth.
    """
    effective = {**cls, **plan.get('decided_params', {})}
    if args.smiles is None and plan.get('smiles'):
        args.smiles = plan['smiles']
    if (args.properties is None or args.properties == 'all') and plan.get('properties'):
        args.properties = ','.join(plan['properties'])
    _apply_plan_hardware(args, plan.get('decided_params', {}))
    return effective

def _apply_plan_hardware(args, dp: dict) -> None:
    """Honor a reasoned plan's D-08_hardware override (engine / gpu_per_run / mpi_ranks in
    decided_params) when the CLI omitted the value. Precedence: CLI > plan > policy — the CLI
    stays authoritative, and resolve_hardware() fills anything still unset from hardware_policy.
    Deterministic plans never carry these keys (make_deterministic_plan.SNAPSHOT_KEYS excludes
    them), so the no-plan path stays byte-identical (tests/test_plan_reproducibility.py)."""
    if args.mpi_ranks is None and dp.get('mpi_ranks') is not None:
        args.mpi_ranks = dp['mpi_ranks']
    if getattr(args, 'engine', None) is None and dp.get('engine') is not None:
        args.engine = dp['engine']
    if args.gpu_ids is None and ('engine' in dp or 'gpu_per_run' in dp):
        (engine, gpu_n) = (dp.get('engine'), dp.get('gpu_per_run'))
        if engine == 'cpu' or gpu_n == 0:
            args.gpu_ids = ''
        elif gpu_n:
            args.gpu_ids = ','.join((str(i) for i in range(int(gpu_n))))
    if getattr(args, 'emc_seed', None) is None and dp.get('emc_seed') is not None:
        args.emc_seed = dp['emc_seed']
    if getattr(args, 'velocity_seed', None) is None and dp.get('velocity_seed') is not None:
        args.velocity_seed = dp['velocity_seed']

def resolve_hardware(args, cls: dict, rules: dict) -> None:
    """Fill mpi_ranks / gpu_ids from the FF×size hardware_policy when the CLI omits
    them, so a run can never default to the mpi=1 anti-pattern. Explicit CLI values
    always win (keeps deterministic-plan output byte-identical — runtime wiring stays
    CLI-authoritative per apply_plan's contract). Specific gpu_ids remain runtime;
    use orchestration/scripts/hardware_runtime.py to claim a non-colliding GPU at submit time."""
    hp = rules.get('hardware_policy')
    if not hp:
        return
    if not hp.get('values_are_benchmarked') or not host_matches(rules):
        saved = hp.get('host') or {}
        saved_desc = f"{saved.get('gpus', '?')}x {saved.get('gpu_model', '?')} / {saved.get('phys_cores', '?')} cores" if saved else '(never calibrated)'
        live = live_host()
        live_desc = f"{live['gpus']}x {live['gpu_model']} / {live['phys_cores']} cores"
        print(f"INFO: hardware_policy was benchmarked on {saved_desc}; you are on {live_desc} (values_are_benchmarked={hp.get('values_are_benchmarked', False)}). Run /calibrate-hardware once to host-match the per-FF engine defaults.", file=sys.stderr)
    ff_raw = cls.get('preferred_ff') or cls.get('forcefield') or ''
    fam = resolve_ff_family(ff_raw, hp)
    pol = hp.get('by_forcefield', {}).get(fam, {})
    if getattr(args, 'engine', None) is None:
        args.engine = pol.get('engine')
    if args.engine != 'kokkos':
        args.engine = 'gpu'
    if args.mpi_ranks is None:
        args.mpi_ranks = pol.get('mpi', 8)
        print(f"INFO: mpi_ranks not given — derived {args.mpi_ranks} from hardware_policy[{fam}] (engine={pol.get('engine')})", file=sys.stderr)
    if args.gpu_ids is None:
        if pol.get('engine') == 'cpu':
            args.gpu_ids = ''
        else:
            n = max(1, int(pol.get('gpu_per_run', 1) or 1))
            args.gpu_ids = ','.join((str(i) for i in range(n)))
        print(f'INFO: gpu_ids not given — derived "{args.gpu_ids}" from hardware_policy[{fam}]; claim free GPU(s) with orchestration/scripts/hardware_runtime.py', file=sys.stderr)

def _pick(arg_val, cls: dict, key: str, default):
    """CLI flag takes precedence over polymer_rules.json; rules over hard default."""
    return arg_val if arg_val is not None else cls.get(key, default)

def _lammps_flags(flags_json: str | None, cls: dict) -> dict:
    if flags_json:
        return json.loads(flags_json)
    ff = cls.get('preferred_ff', '').lower()
    class_ii = 'pcff' in ff or ff in ('compass', 'pcff_ore')
    return {'use_pcff': class_ii, 'use_opls': 'opls' in ff, 'use_trappe': 'trappe' in ff,
            'use_dreiding': 'dreiding' in ff}

@lru_cache(maxsize=512)
def _estimate_tg_group_contribution(smiles: str, timeout: int = 30) -> dict | None:
    """Run rdkit_cli.py's `tg-estimate` in the `radonpy` conda env -- RDKit lives there, not
    in `base`, reached via mol_python.run_in_mol_env() (same seam rules_common.canonicalize uses).
    Returns the parsed result dict, or None on any failure (missing rdkit/conda, timeout,
    unparseable SMILES, no motif match) -- this is an advisory low-confidence estimate,
    never worth crashing plan resolution over."""
    try:
        r = run_in_mol_env(script_path=RDKIT_CLI,
                            args=["tg-estimate", "--smiles", smiles, "--output", "json"],
                            timeout=timeout)
        result = json.loads(r.stdout.strip())
    except Exception:
        return None
    return result if isinstance(result, dict) and 'error' not in result else None

def _exp_tg_point(cls: dict, smiles: str | None=None):
    """Point exp_tg_K value for assess_cooling_contraction's tg_K arg and the tg stage's
    planning-time bracket. A scalar experimental_tg_K (single-member class, or a planning
    agent's overrides.experimental_tg_K pin -- see OVERRIDE_RANGES) always wins outright.
    Otherwise resolves per-member via the run's SMILES. Nothing concrete resolved -- the
    SMILES matched no member, or experimental_tg_K is absent entirely (a genuinely novel
    polymer/class: no experimental Tg exists for ANY member, let alone this one) -> a
    group-contribution estimate from the SMILES itself (low confidence, ~+/-80K), NOT
    another member's value. Estimating from the actual SMILES is honest about what's known
    and what isn't; borrowing a sibling member's exact value is not."""
    tg = cls.get('experimental_tg_K')
    if isinstance(tg, (int, float)):
        return tg
    resolved = resolve_member_value(cls, 'experimental_tg_K', smiles) if smiles else None
    if resolved is not None:
        return resolved
    if smiles:
        est = _estimate_tg_group_contribution(smiles) or {}
        est_tg = est.get('tg_estimated_K')
        if isinstance(est_tg, (int, float)):
            if isinstance(tg, dict):
                members = sorted(k for k, v in tg.items() if isinstance(v, (int, float)))
                reason = f"smiles matched no member among {members}"
            else:
                reason = "experimental_tg_K is not set for this class"
            print(f"INFO: {reason} -- using group-contribution estimate {est_tg}K "
                  f"(confidence={est.get('confidence')}, motifs={est.get('motifs_matched')}) "
                  f"instead of another class member's measured value.", file=sys.stderr)
            return est_tg
    return None

TG_ESTIMATE_UNCERTAINTY_K = 80.0  # rdkit_cli.py tg-estimate's own stated accuracy

def _regime_exp_tg(cls: dict, smiles: str | None=None):
    """Tg for the glassy-vs-rubbery regime call, not _exp_tg_point's bracket estimate. Curated
    values (scalar/matched member) are exact and returned as-is; an estimated value is padded
    by its own +/-80K uncertainty toward glassy, so a borderline estimate defaults safe."""
    tg = cls.get('experimental_tg_K')
    if isinstance(tg, (int, float)):
        return tg
    resolved = resolve_member_value(cls, 'experimental_tg_K', smiles) if smiles else None
    if resolved is not None:
        return resolved
    if smiles:
        est = _estimate_tg_group_contribution(smiles) or {}
        est_tg = est.get('tg_estimated_K')
        if isinstance(est_tg, (int, float)):
            return est_tg + TG_ESTIMATE_UNCERTAINTY_K
    return None

def _exp_density_point(cls: dict, smiles: str | None=None):
    """Point exp_density_gcm3 value (not a ±5% band) for assess_cooling_contraction. A scalar
    (single-member class, or a planning agent's overrides.experimental_density_gcm3 pin -- see
    OVERRIDE_RANGES) always wins outright. Otherwise resolves per-member via the run's SMILES.
    No match -> None, NOT another member's measured density (no group-contribution density
    estimator exists, unlike Tg -- see rules_common.resolve_member_value, the shared
    member-keyed resolver, which refuses rather than guesses). Pin overrides.experimental_density_gcm3 if you've
    reasoned out which member this SMILES actually is."""
    exp = cls.get('experimental_density_gcm3')
    if isinstance(exp, (int, float)):
        return exp
    return resolve_member_value(cls, 'experimental_density_gcm3', smiles) if smiles else None

def _exp_K_range(cls: dict) -> list:
    """exp_K_GPa is a flat {min,max} PER CLASS, not per-member -- e.g. PACR's is scoped to
    PMMA specifically even though PACR also covers PMA (see the class's own note field). There
    is no per-member resolution to get wrong here, only a class-wide range that may be scoped
    to the wrong member of a multi-member class. overrides.exp_K_min_GPa/exp_K_max_GPa (see
    OVERRIDE_RANGES) let the agent pin the correct range once it has checked which member the
    note actually describes; they win outright over the class default when set."""
    lo, hi = cls.get('exp_K_min_GPa'), cls.get('exp_K_max_GPa')
    if isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        return [lo, hi]
    exp = cls.get('exp_K_GPa')
    if isinstance(exp, dict) and 'min' in exp and ('max' in exp):
        return [exp['min'], exp['max']]
    return [None, None]

def _resolve_build_params(args, cls: dict) -> dict:
    """Resolve deterministic molecule-builder arguments."""
    return {'smiles': args.smiles, 'work_dir': args.work_dir or f'{REPO_ROOT}/data/{args.run_name}/lammps', 'preferred_builder': cls.get('preferred_builder', 'emc'), 'preferred_ff': cls.get('preferred_ff', 'gaff2_mod'), 'dp': args.dp or cls.get('dp_typical', 50), 'nchain': args.nchain or cls.get('nchain', 10), 'density_initial_gcm3': _pick(args.density_initial, cls, 'density_initial_gcm3', 0.6), 'build_temperature_K': cls.get('build_temperature_K', 300.0), 'emc_seed': args.emc_seed if getattr(args, 'emc_seed', None) is not None else None, 'charge_method': cls.get('charge_method', 'am1bcc').lower(), 'electrostatics': cls.get('electrostatics', 'pppm'), 'cutoff_A': cls.get('cutoff_A', 12.0), 'dt_fs': cls.get('dt_fs', 1.0), 'phal_patch': args.polymer_class.upper() == 'PHAL', 'lammps_flags': _lammps_flags(args.lammps_flags, cls), 'ff_confidence': 'cited' if cls.get('ff_justification_doi') else 'uncited'}

def _resolve_t_workflow(args, cls: dict) -> float:
    """Equilibration workflow temperature (K). Plan's T_workflow_K wins; otherwise 300 K for
    rubbery (exp_Tg < 300) and T_equil_K for glassy. Mirrors generate_equilibration_workflow,
    Retained as the melt/production REFERENCE temperature: it still feeds the anneal ceiling and
    the regime-adjacent bookkeeping, but it no longer selects a chain shape -- the core chain
    always ends at the melt hold and the cooling chain always ends at npt_final."""
    exp_tg = _regime_tg(args, cls)
    if 'T_workflow_K' in cls:
        return cls['T_workflow_K']
    T_equil = _pick(getattr(args, 'T_equil_K', None), cls, 'T_equil_K', 600.0)
    return 300.0 if isinstance(exp_tg, (int, float)) and exp_tg < 300 else T_equil

def _regime(args, cls: dict) -> str:
    """Single regime oracle: the state of the cell AT THE TEMPERATURE IT IS ASSESSED.

    'rubbery' iff final_T_K > Tg, else 'glassy'. final_T_K is the assessment temperature --
    check_equilibration_comprehensive always gates npt_final, the terminal stage, which
    cool_block always ramps down to final_T_K regardless of regime (see
    _resolve_equil_check_params). 300 K is only its default, not its definition.

    Compare against final_T_K, NOT T_workflow. T_workflow is the melt/production REFERENCE
    temperature -- for a glassy polymer it is the melt-equilibration T (~T_equil), a mid-ramp
    tag, so `T_workflow > Tg` would call every glassy melt rubbery. That trap is why this was
    previously written as `T_workflow <= 300`, which encoded `exp_Tg < 300` indirectly via
    _resolve_t_workflow. Correct in its default case and verified equivalent to this form for
    all 48 curated class/member combinations (see test_regime_matches_the_legacy_proxy_at_300K),
    but it silently misclassifies as soon as final_T_K is set to anything but 300 -- and
    final_T_K is a user-facing production temperature, overridable like any other knob.

    Consumed by the equil-check carve-out (require_rubbery), the analyze-tg data path, the
    single-rate slope-gate exemption, and rubbery-K routing -- one definition, fed everywhere.
    An unresolvable Tg falls to 'glassy', the stricter gate set."""
    tg = _regime_tg(args, cls)
    final_T = _pick(getattr(args, 'final_T_K', None), cls, 'final_T_K', 300.0)
    if not isinstance(tg, (int, float)):
        return 'glassy'
    return 'rubbery' if final_T > tg else 'glassy'


def _tg_is_trustworthy_for_scheduling(args, cls: dict, curated: bool) -> bool:
    """Whether this run's Tg is solid enough to SIZE A PROTOCOL from, not merely to pick a
    regime with.

    A curated experimental value always is. A group-contribution estimate is only when the
    estimator itself says so: it returns confidence='very_low' with an explicit warning
    ("temperature estimates unreliable -- leave global_defaults unchanged") once more than 30%
    of heavy atoms match no motif, and 633 of the 1077 polymers in RadonPy's PI1070 set trip
    that -- 59% of the real chemical space. Sizing a sweep window or a melt temperature from
    one of those would be worse than the class constant, which is at least a considered value
    for related chemistry.

    Note the asymmetry with the regime call: _regime uses the estimate at ANY confidence,
    because there the question is only which side of Tg the assessment sits on, the estimate is
    already padded toward glassy by TG_ESTIMATE_UNCERTAINTY_K, and an unresolvable answer falls
    to the stricter gate set. Here the number itself is the protocol, so it has to be earned."""
    if curated:
        return True
    smiles = getattr(args, 'smiles', None)
    if getattr(args, 'exp_tg_K', None) is not None:
        return True
    if not smiles:
        return False
    est = _estimate_tg_group_contribution(smiles) or {}
    return est.get('confidence') not in (None, 'very_low', 'unavailable')


def _regime_tg(args, cls: dict):
    """The Tg the regime call is made against: an explicit --exp_tg_K wins, else the curated
    or group-contribution-estimated value (_regime_exp_tg already pads an estimate toward
    glassy by its own uncertainty). Split out so the regime and _resolve_t_workflow resolve Tg
    identically rather than by two similar-looking code paths."""
    override = getattr(args, 'exp_tg_K', None)
    if override is not None:
        return override
    return _regime_exp_tg(cls, getattr(args, 'smiles', None))

def _is_glassy(args, cls: dict) -> bool:
    """Whether the BM stages treat this cell as glassy. The orchestrator's `--is_glassy`, set from
    the thermal track's measured Tg, wins; with the flag absent the regime oracle decides. An
    argparse default cannot: it applies to every class alike, so a rubbery run silently reads as
    glassy and takes the Murnaghan/deform glassy branch."""
    flag = getattr(args, 'is_glassy', None)
    if flag is not None:
        return str(flag).lower() not in ('false', '0', 'no')
    return _regime(args, cls) == 'glassy'

def _velocity_seed(args) -> int:
    """The equilibration chain's `velocity all create` seed. generate_equilibration_workflow
    rejects a null seed, so resolve one here: the plan's pinned value if it has one, else a
    value derived from run_name — stable across retries, distinct per replicate."""
    pinned = getattr(args, 'velocity_seed', None)
    if pinned is not None:
        return int(pinned)
    digest = hashlib.sha256(args.run_name.encode()).hexdigest()
    return 10000 + int(digest, 16) % 989999

ANNEAL_MARGIN_K = 100.0
"""Minimum required margin between T_anneal_high_K and T_workflow_K -- see the matching hard
validation guard in generate_equilibration_workflow. Enforced HERE (self-healing at the
planning layer) as well as there (backstop): a scientifically meaningful choice like the
anneal peak temperature should be decided once, visibly, not patched deep in the generator."""

MD_TG_OFFSET_K = 120.0
"""How far above the experimental Tg an MD sweep actually finds the transition.

The glass transition is kinetic: it happens where the chains' relaxation time exceeds the time
the cooling schedule allows. MD cools at 10-100 K/ns against a DSC experiment's ~0.00017 K/ns
-- five to six decades faster -- so the transition freezes in high, by an observed 80-120 K
(PROPERTIES.md reports it as tg_offset_corrected_K, an annotation never folded into PASS/FAIL).
The upper bound is used here because a sweep window is sized to CONTAIN the transition: a
window that stops short finds no breakpoint at all."""

TG_BRANCH_K = 150.0
"""How much temperature range the sweep keeps on each side of the transition.

The Tg fit is bilinear: a glassy branch, a rubbery branch, and a breakpoint between them. Each
branch needs enough points to define a slope, so the window is sized as a margin around the MD
transition rather than as a ratio of Tg or an offset from the melt temperature. At the usual
20 K step this is 7-8 points above the breakpoint and ~11 below -- the glassy side gets 1.5x
because its slope is the shallower of the two (a smaller thermal expansion coefficient) and so
needs a longer lever arm to resolve.

Not a physical constant: it is a fit-quality budget, and the knob to widen if a class shows
systematically poor r-squared rather than lowering tg_min_steps_per_T."""


def _is_curated_member(cls: dict, smiles: str | None) -> bool:
    """Whether this SMILES matches a member the class actually curated a Tg for.

    The distinction the temperature schedule turns on. A class's T_equil_K was chosen to clear
    the melting point of its curated members -- the class notes name those Tm values explicitly
    ("PET Tm=533 K ... T_equil=620 K exceeds all Tm values"). For a curated member that
    constant is known-adequate and must not be second-guessed by a +/-80 K group-contribution
    estimate. For a SMILES the class never curated, it is an extrapolation, and a stiffer
    novel member can need more."""
    if not smiles:
        return False
    try:
        return resolve_member_value(cls, 'experimental_tg_K', smiles) is not None
    except Exception:  # noqa: BLE001 -- a matcher failure means "not curated", never a crash
        return False


def temperature_schedule(args, cls: dict) -> dict:
    """The run's whole temperature schedule, adapted to this SMILES and the requested state.

    Single place that decides the temperatures the equilibration and cooling chains are built
    from, so they cannot drift out of coherence with each other:

      final_T_K      the ASSESSMENT temperature -- what the cooling stage ramps to and gates at
                     (npt_final). 300 K is its default, not its definition.
      T_equil_K      the melt-equilibration temperature. Must clear this polymer's melting point,
                     which group contribution cannot see; the class constant therefore always
                     acts as a FLOOR and is used unchanged for a curated member. For a novel
                     SMILES it can only be RAISED, never lowered: max(Tg+200, 1.5*Tg) -- the
                     additive term governs low-Tg polymers, Boyer's Tm/Tg ~ 1.5 ratio governs
                     high-Tg ones, where a fixed +200 K undershoots (PEEK: Tg 418 -> +200 = 618
                     vs Tm 616).
      T_melt_hold_K  where the core equilibration chain ENDS and everything downstream starts:
                     the gated melt cell, the Tg staircase's first point, and the cooling stage's
                     input. See the derivation note below.
      T_anneal_high  the anneal ceiling, ANNEAL_MARGIN_K above whichever of T_equil/final_T_K is
                     higher, and never below T_melt_hold_K (npt_melt_ramp descends to it).
                     Raising it is cheap and lowering it is not the saving it looks like:
                     25 K of ceiling costs one cool block (~200k steps) while ONE avoided
                     anneal_hold extension saves 1-2.5M, so break-even sits 125-312 K out. The
                     ceiling is therefore bounded by physical validity (thermal degradation,
                     Class II quartic bond instability, timestep validity), never by compute.

    Returns the resolved values plus `schedule_source`, so a plan records whether a temperature
    came from the class constant or was raised for a novel SMILES.
    """
    smiles = getattr(args, 'smiles', None)
    tg = _regime_tg(args, cls)
    curated = _is_curated_member(cls, smiles)

    final_T = _pick(getattr(args, 'final_T_K', None), cls, 'final_T_K', 300.0)
    class_equil = _pick(getattr(args, 'T_equil_K', None), cls, 'T_equil_K', 600.0)

    trustworthy = _tg_is_trustworthy_for_scheduling(args, cls, curated)

    T_equil, source = class_equil, 'class_default'
    if not curated and trustworthy and isinstance(tg, (int, float)):
        needed = max(tg + 200.0, 1.5 * tg)
        if needed > class_equil:
            T_equil, source = needed, 'raised_for_novel_smiles'

    # T_melt_hold_K -- the melt the whole run hangs off. It must clear the MD glass transition,
    # not merely the melting point, because the Tg staircase now STARTS here and runs the entire
    # descent: a melt hold below the MD transition would begin the sweep inside the glass and the
    # bilinear fit would find no breakpoint (TG_NOT_REPORTABLE -- loud, but a wasted run).
    #
    # Two sources, in order of how far each can be trusted:
    #   trustworthy per-SMILES Tg -> Tg + 200 K. The MD transition sits MD_TG_OFFSET_K (120 K)
    #     above the experimental Tg at accessible cooling rates, so this clears it by 80 K.
    #   otherwise -> md_tg_ceiling_K, this class's own bound on how hot its chemistry's MD Tg
    #     gets (formerly tg_t_high_K, back when it was the sweep's top). An untrustworthy
    #     estimate is 59% of RadonPy's PI1070 set, and for 14 of the 21 classes this constant
    #     sits ABOVE T_equil_K -- POXI is the worked example: T_equil 500 K against a class
    #     bound of 600 K, with 24 of 66 scored POXI polymers having an MD Tg above 500 K.
    #
    # T_equil_K floors both: it carries melting-point knowledge Tg cannot see (PE's Tg is 195 K
    # and it melts near 410 K), and for a novel trustworthy SMILES it has already absorbed the
    # Tg+200 term above -- so this only ever LIFTS a CURATED member whose own Tg runs hot for its
    # class (11 of the 51 curated members; PEI/Ultem is the load-bearing case, whose 550 K class
    # melt left only 62 K of rubbery branch above a Tg of 488 K).
    if trustworthy and isinstance(tg, (int, float)):
        melt_clearance = tg + 200.0
    else:
        melt_clearance = _pick(getattr(args, 'md_tg_ceiling_K', None), cls,
                               'md_tg_ceiling_K', 600.0)
    T_melt_hold = max(T_equil, float(melt_clearance))

    # Only the sweep's COLD bound is a knob now. Its hot bound is T_melt_hold_K by construction:
    # the staircase starts at the melt hold and cools, so there is no separate top to size.
    # (tg_t_high_K used to live here. It was the sweep's top AND, via a ceiling headroom term,
    # the thing that guaranteed the cooldown tagged a waypoint the sweep could start from. Both
    # jobs are gone: the sweep owns its own descent from a named, gated stage.)
    tg_low = _pick(getattr(args, 'tg_t_low_K', None), cls, 'tg_t_low_K', 200)
    # The FIT window's top -- an analysis bound, never a start temperature. The sweep descends
    # from the melt hold and every bin is simulated and reported; only bins above this are kept
    # out of the bilinear fit. It exists because curve_fit is unweighted: for a low-Tg member of
    # a hot class the melt branch would otherwise dominate the point count, and on synthetic
    # curves with realistic melt curvature that biases Tg by -15 to -36 K, against -1 to -3 K
    # over the sized window. Sized around the MD transition (Tg + MD_TG_OFFSET_K), which is
    # where the rubbery branch is still straight; None when no trustworthy Tg sizes it, in
    # which case the whole descent is fitted as before.
    tg_fit_top = None
    window_source = 'class_default'
    explicit_window = getattr(args, 'tg_t_low_K', None) is not None
    if not explicit_window and trustworthy and isinstance(tg, (int, float)):
        # Sized around the MD transition, not around the melt: the bilinear fit needs a straight
        # run of points BELOW the breakpoint, and 1.5x TG_BRANCH_K is the glassy-side lever arm.
        est_low = round(max(100.0, tg + MD_TG_OFFSET_K - 1.5 * TG_BRANCH_K))
        if est_low < tg - 20:
            tg_low = est_low
            # Clamped to the melt hold: there are no bins above it to fit. For most curated
            # members the clamp binds (the melt clears the MD transition by 80 K, the unclamped
            # window wanted 150 K), so they fit their whole descent -- correctly, because a
            # descent that short has no featureless melt branch to be dominated by. The bound
            # only bites for a low-Tg member of a hot class, which is exactly the shape it
            # exists for: PTFE fits 100-430 K of a 100-700 K sweep.
            tg_fit_top = min(round(tg + MD_TG_OFFSET_K + TG_BRANCH_K), T_melt_hold)
            window_source = 'curated_tg' if curated else 'estimated_tg'

    ceiling_terms = {
        'class_default': _pick(getattr(args, 'T_anneal_high_K', None), cls,
                               'annealing_T_high_K', 700.0),
        'melt_margin': T_equil + ANNEAL_MARGIN_K,
        'assessment_margin': final_T + ANNEAL_MARGIN_K,
        # T_workflow stays explicit: it is normally T_equil (glassy) or final_T (rubbery), so it
        # is already covered -- but it is independently overridable, and dropping it would
        # silently lower the ceiling for a plan that pins T_workflow above both.
        'workflow_margin': _resolve_t_workflow(args, cls) + ANNEAL_MARGIN_K,
        # No ANNEAL_MARGIN on this one, deliberately. The anneal soak's job is to sit above the
        # MELT-EQUILIBRATION temperature, and melt_margin already puts it there. This term only
        # guarantees npt_melt_ramp is a DESCENT (ceiling >= melt hold) for a class whose
        # md_tg_ceiling_K or per-SMILES Tg pushes the melt hold above T_equil + 100. It does not
        # bind for any of the 21 classes or 51 curated members today -- which is why this whole
        # redesign moves no class ceiling at all -- and it exists so that a future edit to
        # md_tg_ceiling_K or T_equil_K cannot silently invert the ramp.
        'melt_hold_floor': T_melt_hold,
    }
    ceiling_source = max(ceiling_terms, key=lambda k: ceiling_terms[k])
    T_anneal = ceiling_terms[ceiling_source]

    return {'final_T_K': final_T, 'T_equil_K': T_equil, 'T_melt_hold_K': T_melt_hold,
            'T_anneal_high_K': T_anneal, 'tg_t_low_K': tg_low,
            'tg_fit_top_K': tg_fit_top,
            'cool_block_dT_K': float(cls.get('cool_block_dT_K') or 25.0),
            'tg_K': tg, 'tg_is_curated': curated, 'tg_trustworthy': trustworthy,
            'schedule_source': source, 'window_source': window_source,
            'ceiling_source': ceiling_source}


def select_primary_tg_rate_index(cls: dict) -> int:
    """Which entry of tg_rates_K_per_ns this run actually sweeps at.

    ONE definition, because three places need it and they must not drift: do_thermal (which rate
    the staircase runs), _resolve_equil_params (which rate cool_block cools at, below), and
    cost_model (which rate to price). Highest configured rate by default; a class carrying
    tg_slope_gate_fallback="slowest_rate" runs rates[0] instead, and an explicit
    tg_primary_rate_index pins it outright.
    """
    rates = cls.get('tg_rates_K_per_ns') or []
    if not rates:
        return 0
    planned = cls.get('tg_primary_rate_index')
    if planned is not None:
        return int(planned)
    return 0 if cls.get('tg_slope_gate_fallback') == 'slowest_rate' else len(rates) - 1


def rate_matched_cool_block_hold_steps(cls: dict, dt_fs: float, dT_K: float):
    """Steps per cool_block so the cooldown runs at this class's own Tg-sweep rate.

    The cooling stage's descent and the Tg staircase are two descents from the SAME melt cell,
    at the same temperatures, differing only in what is sampled along the way. Running them at
    different rates would mean a run's density and its Tg describe glasses with two different
    thermal histories, and glass density is rate-dependent (~1.1% per decade, measured over 21
    archived multi-rate sweeps across 8 chemistries) -- so the match is not cosmetic.

    It also makes density comparable ACROSS runs: a density-only run has no staircase, but its
    cooldown runs at the rate the staircase would have used, so its glass has the same thermal
    history as a Tg run's.

    Returns None when the class configures no rates (nothing to match); the caller then falls
    through to generate_equilibration_workflow's own atom-count tier default.
    """
    rates = cls.get('tg_rates_K_per_ns') or []
    if not rates or not dT_K or not dt_fs:
        return None
    rate = rates[select_primary_tg_rate_index(cls)]
    if not rate:
        return None
    return int(round(dT_K / (rate * dt_fs * 1e-06)))


def _resolve_equil_params(args, cls: dict) -> dict:
    """Resolve the CORE equilibration chain's arguments.

    The core chain ends at the melt hold. Everything about the descent to final_T_K -- the
    cool blocks, nvt_kinetic_stability, npt_final -- belongs to the `cool` resolver now, and
    those keys are deliberately absent here rather than passed and ignored.
    """
    dt = _pick(args.dt_fs, cls, 'dt_fs', 1.0)
    sched = temperature_schedule(args, cls)

    def _step_pick(name):
        """Direct step-count override -- None selects generate_equilibration_workflow's own
        atom-count tier default."""
        return _pick(getattr(args, name, None), cls, name, None)

    return {
        'data_path': args.data_path,
        'emc_params_path': getattr(args, 'emc_params_path', None),
        'lammps_flags': _lammps_flags(args.lammps_flags, cls),
        'use_long_range_electrostatics': cls.get('electrostatics', 'pppm') == 'pppm',
        'work_dir': args.work_dir or f'{REPO_ROOT}/data/{args.run_name}/lammps/equil',
        'dt_fs': dt,
        'T_equil_K': sched['T_equil_K'],
        'T_melt_hold_K': sched['T_melt_hold_K'],
        'T_anneal_high_K': sched['T_anneal_high_K'],
        'anneal_margin_K': ANNEAL_MARGIN_K,
        'T_workflow_K': _resolve_t_workflow(args, cls),
        'P_equil_atm': cls.get('P_equil_atm', 1.0),
        'compression_max_pressure_atm': cls.get('compression_max_pressure_atm', 50000.0),
        'thermostat_damp_fs': cls.get('thermostat_damp_fs', 100.0),
        'barostat_damp_fs': cls.get('barostat_damp_fs', 1000.0),
        'warmup_steps': _step_pick('warmup_steps'),
        'densify_ramp_steps': _step_pick('densify_ramp_steps'),
        'densify_check_every_steps': _step_pick('densify_check_every_steps'),
        'densify_steps_cap': _step_pick('densify_steps_cap'),
        'ff_activate_npt_steps': _step_pick('ff_activate_npt_steps'),
        'anneal_heat_steps': _step_pick('anneal_heat_steps'),
        'anneal_check_every_steps': _step_pick('anneal_check_every_steps'),
        'anneal_cap_steps': _step_pick('anneal_cap_steps'),
        # The melt tail. npt_melt_ramp is one-shot (ceiling -> melt hold); the two holds are
        # adaptive, first-block/cap pairs like every other adaptive stage.
        'melt_ramp_steps': _step_pick('melt_ramp_steps'),
        'melt_hold_min_steps': _step_pick('melt_hold_min_steps'),
        'melt_hold_cap_steps': _step_pick('melt_hold_cap_steps'),
        'nvt_melt_min_steps': _step_pick('nvt_melt_min_steps'),
        'nvt_melt_cap_steps': _step_pick('nvt_melt_cap_steps'),
        'gpu_ids': args.gpu_ids,
        'mpi_ranks': args.mpi_ranks,
        'engine': args.engine,
        'velocity_seed': _velocity_seed(args),
        'cutoff_A': cls.get('cutoff_A', 12.0),
        'nchain': args.nchain or cls.get('nchain', 10),
        'exp_density_gcm3': _exp_density_point(cls, args.smiles),
        # minimize.in's ETOL/FTOL/MAXITER/MAXEVAL -- defaults match script_generator.py's own.
        # raise_minimize_tolerance (workflow_engine.py) escalates these via decided_params on
        # a MINIMIZE_NOT_CONVERGED finding; cls here is the post-apply_plan overlay, so a
        # remedy-written decided_params value is picked up automatically on resubmission.
        'minimize_etol': _pick(getattr(args, 'minimize_etol', None), cls, 'minimize_etol', 1e-6),
        'minimize_ftol': _pick(getattr(args, 'minimize_ftol', None), cls, 'minimize_ftol', 1e-6),
        'minimize_maxiter': int(_pick(getattr(args, 'minimize_maxiter', None), cls,
                                      'minimize_maxiter', 50000)),
        'minimize_maxeval': int(_pick(getattr(args, 'minimize_maxeval', None), cls,
                                      'minimize_maxeval', 100000)),
        # anneal_hold MSID-convergence gate (opt-in, off by default -- see
        # _anneal_hold_adaptive_extend in run_campaign.py). Defaults sourced from PEG1/POXI
        # Phase 0 validation: large-s MSID rose 0.663->0.849->0.923 across two 2.5ns
        # restart-continued extensions and plateaued (0.923/0.915/0.901, ~1-2.5% relative
        # jitter at short separation) once inside the +-20% gaussian_pass band --
        # anneal_hold_stability_pct=5.0 sits above that observed noise floor with margin.
        'anneal_hold_msid_gate_enabled': bool(cls.get('anneal_hold_msid_gate_enabled', False)),
        'anneal_hold_max_extensions': int(cls.get('anneal_hold_max_extensions', 2)),
        'anneal_hold_stability_pct': cls.get('anneal_hold_stability_pct', 5.0),
        'anneal_hold_extend_ns': cls.get('anneal_hold_extend_ns', 2.5),
        # Rg veto on the gate's STABLE early-stop path only (never on PASS, never a second
        # AND-condition on the whole gate): if MSID's pairwise slope-diff would otherwise
        # declare STABLE, but mean_Rg_A is still moving more than this % between the last two
        # probes, keep extending instead -- a flat MSID slope isn't proof the chain has
        # explored its conformational space if Rg hasn't settled alongside it. Deliberately
        # permissive placeholder: unlike anneal_hold_stability_pct (calibrated from Phase 0's
        # own slope-jitter data), no real multi-probe Rg-drift-magnitude data exists yet --
        # PEG1_gate_validation's only live run passed MSID on its first probe (0 extensions),
        # so there's a single Rg data point, not a trend. Tighten once a real run with >=2
        # extensions supplies an actual jitter floor to calibrate against (same reasoning
        # that set anneal_hold_stability_pct=5.0, just not yet available for Rg).
        'anneal_hold_rg_veto_pct': cls.get('anneal_hold_rg_veto_pct', 10.0),
    }


def _resolve_cool_params(args, cls: dict) -> dict:
    """Resolve the COOLING chain's arguments: melt hold -> final_T_K, then the assessment cell.

    Runs only when something downstream needs a cell at the assessment temperature (a density
    at final_T_K, or any mechanical property). A melt-only run never reaches this resolver.
    """
    dt = _pick(args.dt_fs, cls, 'dt_fs', 1.0)
    sched = temperature_schedule(args, cls)
    dT = _pick(getattr(args, 'cool_block_dT_K', None), cls, 'cool_block_dT_K', None)

    def _step_pick(name):
        return _pick(getattr(args, name, None), cls, name, None)

    return {
        # The melt-start cell the equilibration stage published (nvt_melt_hold_out.data). The
        # flat-convention fallback is --dry-run only; in real execution CampaignStageExecutor
        # sets args.data_path from the accepted equilibration manifest.
        'data_path': (getattr(args, 'melt_start_data_path', None) or args.data_path
                      or f'{REPO_ROOT}/data/{args.run_name}/lammps/equil/nvt_melt_hold/'
                         'nvt_melt_hold_out.data'),
        'lammps_flags': _lammps_flags(args.lammps_flags, cls),
        'use_long_range_electrostatics': cls.get('electrostatics', 'pppm') == 'pppm',
        'work_dir': args.work_dir or f'{REPO_ROOT}/data/{args.run_name}/lammps/cool',
        'dt_fs': dt,
        'T_melt_hold_K': sched['T_melt_hold_K'],
        'final_T_K': sched['final_T_K'],
        'P_equil_atm': cls.get('P_equil_atm', 1.0),
        'thermostat_damp_fs': cls.get('thermostat_damp_fs', 100.0),
        'barostat_damp_fs': cls.get('barostat_damp_fs', 1000.0),
        'cool_block_dT_K': dT,
        # An explicit plan/class value still wins; otherwise derive it from this class's own
        # sweep rate rather than falling to the generator's flat 2e5/dt tier default.
        'cool_block_hold_steps': (_step_pick('cool_block_hold_steps')
                                  or rate_matched_cool_block_hold_steps(
                                      cls, dt, cls.get('cool_block_dT_K') or 25.0)),
        'cool_block_hold_cap_steps': _step_pick('cool_block_hold_cap_steps'),
        'stage7_min_steps': _step_pick('stage7_min_steps'),
        'stage7_cap_steps': _step_pick('stage7_cap_steps'),
        'stage8_min_steps': _step_pick('stage8_min_steps'),
        'stage8_cap_steps': _step_pick('stage8_cap_steps'),
        'gpu_ids': args.gpu_ids,
        'mpi_ranks': args.mpi_ranks,
        'engine': args.engine,
        'velocity_seed': _velocity_seed(args),
        'cutoff_A': cls.get('cutoff_A', 12.0),
        'nchain': args.nchain or cls.get('nchain', 10),
        'exp_density_gcm3': _exp_density_point(cls, args.smiles),
    }

def _resolve_tg_rate(args, cls: dict):
    """Resolve the selected cooling rate + a per-rate output-dir suffix for multi-rate
    Tg sweeps. Returns (selected_rate | None, rate_suffix). When --tg_rate_index is unset,
    suffix is "" so the single-rate path stays byte-identical to the legacy pipeline."""
    tg_rates = cls.get('tg_rates_K_per_ns', [])
    rate_idx = getattr(args, 'tg_rate_index', None)
    if rate_idx is not None and tg_rates and (rate_idx < len(tg_rates)):
        selected_rate = tg_rates[rate_idx]
        return (selected_rate, f'_r{int(selected_rate)}')
    return (None, '')

def _melt_start_data_path(args) -> str:
    """The cell the core equilibration chain ends on: nvt_melt_hold_out.data.

    Real execution gets this from the accepted equilibration manifest (CampaignStageExecutor
    sets args.melt_start_data_path); args.data_path is the same file by then. The flat-convention
    fallback is --dry-run only, where no attempt directory exists yet.
    """
    return (getattr(args, 'melt_start_data_path', None) or getattr(args, 'data_path', None)
            or f'{REPO_ROOT}/data/{args.run_name}/lammps/equil/nvt_melt_hold/nvt_melt_hold_out.data')


def _resolve_tg_params(args, cls: dict) -> dict:
    """Resolve deterministic single-rate Tg sweep arguments."""
    dt = _pick(args.dt_fs, cls, 'dt_fs', 1.0)
    tg_rates = cls.get('tg_rates_K_per_ns', [])
    rate_idx = getattr(args, 'tg_rate_index', None)
    (selected_rate, rate_suffix) = _resolve_tg_rate(args, cls)
    t_step = _pick(args.tg_t_step_K, cls, 'tg_t_step_K', 20)
    floor = cls.get('tg_min_steps_per_T', 200000)
    # The staircase starts AT the melt hold and cools to tg_t_low_K -- one continuous descent
    # from the cell the equilibration stage gated, with no reheat and no mid-ramp waypoint. Both
    # bounds come from the shared temperature schedule so the thermal and equilibration stages
    # cannot disagree about this polymer's melt.
    _sched = temperature_schedule(args, cls)
    if selected_rate is not None:
        n_steps_per_t = int(t_step / (selected_rate * dt * 1e-06))
    else:
        n_steps_per_t = _pick(args.tg_steps_per_t, cls, 'tg_steps_per_t', 500000)
    work_dir = args.work_dir or f'{REPO_ROOT}/data/{args.run_name}/lammps/thermal'
    return {'lammps_flags': _lammps_flags(args.lammps_flags, cls), 'use_long_range_electrostatics': cls.get('electrostatics', 'pppm') == 'pppm', 'work_dir': work_dir, 'dt_fs': dt, 'tg_rates_K_per_ns': tg_rates, 'tg_rate_index': rate_idx, 'selected_rate_K_per_ns': selected_rate, 'tg_sweep_dir': f'{work_dir}/tg_sweep{rate_suffix}', 'T_start_K': _sched['T_melt_hold_K'], 'T_end_K': _sched['tg_t_low_K'], 'tg_window_source': _sched['window_source'], 'T_step_K': t_step, 'n_steps_per_t': n_steps_per_t, 'tg_min_steps_per_T': floor, 'below_steps_floor': selected_rate is not None and n_steps_per_t < floor, 'pressure_atm': cls.get('P_equil_atm', 1.0), 'thermostat_damp_fs': cls.get('thermostat_damp_fs', 100.0), 'barostat_damp_fs': cls.get('barostat_damp_fs', 1000.0), 'equil_data_path': _melt_start_data_path(args), 'gpu_ids': args.gpu_ids, 'mpi_ranks': args.mpi_ranks, 'engine': args.engine, 'velocity_seed': _velocity_seed(args), 'cutoff_A': cls.get('cutoff_A', 12.0),
            'T_workflow_K': _resolve_t_workflow(args, cls),
            'final_T_K': _pick(getattr(args, 'final_T_K', None), cls, 'final_T_K', 300.0),
            'tg_per_t_max_extensions': int(cls.get('tg_per_t_max_extensions', 2)),
            'tg_per_t_stability_pct': cls.get('tg_per_t_stability_pct', 1.0),
            'tg_per_t_min_n_eff': cls.get('tg_per_t_min_n_eff', 5.0)}

def _resolve_deform_params(args, cls: dict) -> dict:
    """Resolve deterministic deformation arguments."""
    return {'deform_rate_mode': args.deform_rate_mode, 'equil_data_path': args.data_path, 'lammps_flags': _lammps_flags(args.lammps_flags, cls), 'work_dir': args.work_dir or f'{REPO_ROOT}/data/{args.run_name}/lammps/mechanical', 'is_glassy': _is_glassy(args, cls), 'K_deform_rate_inv_s': _pick(args.K_deform_rate_inv_s, cls, 'K_deform_rate_inv_s', 100000000.0), 'K_deform_rate_slow_inv_s': cls.get('K_deform_rate_slow_inv_s', 'null'), 'K_strain_max': _pick(args.K_strain_max, cls, 'K_strain_max', 0.03), 'deform_eq_steps': int(cls.get('deform_eq_steps', 200000)), 'deform_strain_start': cls.get('deform_strain_start', 0.002), 'deform_avg_window': int(cls.get('deform_avg_window', 2000)), 'thermostat_damp_fs': cls.get('thermostat_damp_fs', 100.0), 'dt_fs': _pick(args.dt_fs, cls, 'dt_fs', 1.0), 'gpu_ids': args.gpu_ids, 'mpi_ranks': args.mpi_ranks, 'engine': args.engine, 'velocity_seed': _velocity_seed(args), 'cutoff_A': cls.get('cutoff_A', 12.0)}

def _run_graphs_dir(args) -> str:
    """Run-level graphs directory, shared by every plotting stage -- NOT output_dir with its
    /raw/ leaf swapped, which (output_dir being per-attempt) only ever produced another
    per-attempt path. Stages that never plot (build, summary) never call this."""
    return f'{REPO_ROOT}/data/{args.run_name}/graphs'

def _resolve_analyze_tg_params(args, cls: dict) -> dict:
    """Resolve deterministic per-rate Tg analysis arguments."""
    (selected_rate, rate_suffix) = _resolve_tg_rate(args, cls)
    raw_suffix = f'tg_r{int(selected_rate)}/' if selected_rate is not None else ''
    output_dir = args.output_dir or f'{REPO_ROOT}/data/{args.run_name}/raw/{raw_suffix}'
    # Flat, unlike output_dir -- generate_run_summary's rel_fig() looks for tg_fit.png directly
    # under the run-level graphs/ dir; a rate-suffixed graphs/tg_r40/ would hide it from summary
    # the same way the old per-attempt scoping did.
    graphs_dir = _run_graphs_dir(args)
    lammps_base = f'{REPO_ROOT}/data/{args.run_name}/lammps'
    # tg_sweep_dir mirrors _resolve_tg_params' own formula exactly -- analyze-tg reads the same
    # attempt work_dir the tg stage just wrote its sweep into, not a flat-convention guess.
    # (Previously this read args.data_path -- the EQUILIBRATION attempt's structure file, always
    # non-null during real execution -- so it never fell through to the intended tg_sweep.log
    # path at all; extract_thermal then failed parsing a .data file for thermo rows. PE1 hit
    # this live, 2026-08-17.)
    tg_work_dir = args.work_dir or f'{lammps_base}/thermal'
    tg_sweep_dir = f'{tg_work_dir}/tg_sweep{rate_suffix}'
    tg_log = f'{tg_sweep_dir}/tg_sweep.log'
    # The structure file extract_thermal reads is the cell the SWEEP started from -- the melt
    # hold -- not the assessment cell. args.equil_data_path holds the real accepted output
    # during execution; the flat-convention guess is a --dry-run-only fallback.
    equil_data = args.equil_data_path or _melt_start_data_path(args)
    per_t_dump = f'{tg_sweep_dir}/per_t_structs.dump'
    return {'selected_rate_K_per_ns': selected_rate, 'tg_rate_index': args.tg_rate_index, 'tg_log_path': tg_log, 'tg_data_file': equil_data, 'per_t_dump_file': per_t_dump, 'enthalpy_col': getattr(args, 'enthalpy_col', None) or 'Enthalpy', 'backbone_types': args.backbone_types or cls.get('backbone_types'), 'output_dir': output_dir, 'graphs_dir': graphs_dir, 'method_gap_exempt': bool(cls.get('tg_slope_gate_fallback') == 'slowest_rate'),
            'fit_t_max_K': temperature_schedule(args, cls)['tg_fit_top_K']}

def _derive_npt_prod_log_path(args, effective_data_path, lammps_base: str) -> str:
    """Shared by _resolve_equil_check_params/_resolve_murnaghan_params/
    _resolve_analyze_bm_params -- these three independently derived this same path
    (a prior bug from that duplication was already fixed twice, see the comments in
    the equil-check and analyze-bm resolvers below). ``effective_data_path`` is each
    caller's own already-resolved data path (args.data_path, or that resolver's own
    dry-run default when args.data_path is unset) -- not re-derived here, so this
    helper's behavior is identical to what each resolver already computed inline."""
    if args.npt_prod_log:
        return args.npt_prod_log
    if effective_data_path and effective_data_path.endswith('_out.data'):
        return effective_data_path[:-len('_out.data')] + '.log'
    return f'{lammps_base}/cool/npt_final/npt_final.log'


def _resolve_equil_check_params(args, cls: dict) -> dict:
    """Resolve the MELT gate's arguments.

    The core equilibration chain ends at the melt hold, and this is what adjudicates it. The
    cell is a melt by construction (T_melt_hold_K clears the MD transition), so `regime` is
    'melt' unconditionally -- NOT resolve_regime/_regime, which fall to 'glassy' whenever Tg is
    unresolvable, and that is the common case for a novel SMILES. The melt clause is the one
    place chain relaxation is physically attainable, so rg and ct bind there (see
    enforce_gate.BINDING_MELT); at the assessment temperature they cannot and do not.

    check_equilibration_comprehensive reads two trajectories, and the split is the same one it
    has always used, just moved up the chain: melt_dump_path is nvt_melt_hold's fixed-volume
    window, for the ensemble-sensitive checks (MSD/kinetic-trap, C(t)); struct_dump_path is
    npt_melt_hold's own trajectory, for the ensemble-insensitive per-frame geometry checks
    (Rg/MSID/R_ee/torsion/P2/density_homogeneity/finite_size). A barostatted trajectory
    affine-scales coordinates every step and would contaminate cumulative CoM displacement,
    which is why the MSD window has to be the NVT one.

    No melt_data_path: the cooling-contraction probe compares a melt against a glass, and there
    is no glass yet. enforce_live skips it on a falsy melt_data regardless of regime.
    """
    output_dir = args.output_dir or f'{REPO_ROOT}/data/{args.run_name}/raw/'
    graphs_dir = _run_graphs_dir(args)
    ct_decay = cls.get('ct_min_decay_melt', 0.1) if cls.get('ct_gate_reliable', True) else None
    lammps_base = f'{REPO_ROOT}/data/{args.run_name}/lammps'
    sched = temperature_schedule(args, cls)
    hold = 'npt_melt_hold'
    npt_prod_data_path = args.data_path or f'{lammps_base}/equil/{hold}/{hold}_out.data'
    npt_prod_log_path = _derive_npt_prod_log_path(args, npt_prod_data_path, lammps_base)
    return {'output_dir': output_dir, 'graphs_dir': graphs_dir, 'ct_min_decay_melt': ct_decay,
            'cutoff_A': cls.get('cutoff_A'),
            'npt_prod_log_path': npt_prod_log_path,
            'npt_prod_data_path': npt_prod_data_path,
            'melt_dump_path': (args.npt_prod_dump
                               or f'{lammps_base}/equil/nvt_melt_hold/nvt_melt_hold.dump'),
            'struct_dump_path': (getattr(args, 'struct_dump_path', None)
                                 or f'{lammps_base}/equil/{hold}/{hold}.dump'),
            'melt_data_path': None,
            'npt_prod_temp_K': sched['T_melt_hold_K'],
            'T_melt_hold_K': sched['T_melt_hold_K'],
            'T_workflow_K': _resolve_t_workflow(args, cls),
            'exp_tg_point_K': _exp_tg_point(cls, getattr(args, 'smiles', None)),
            'regime': 'melt',
            'dp': getattr(args, 'dp', None) or cls.get('dp_typical'),
            'ct_gate_reliable': cls.get('ct_gate_reliable', True),
            'backbone_types': args.backbone_types or cls.get('backbone_types'),
            'dt_fs': _pick(args.dt_fs, cls, 'dt_fs', 1.0)}


def _resolve_cool_check_params(args, cls: dict) -> dict:
    """Resolve the ASSESSMENT gate's arguments -- the cell at final_T_K, after the cooldown.

    This is the gate that used to be the only one. npt_final is unconditionally the cooling
    chain's terminal stage (cool_block always ramps to final_T_K regardless of regime), so
    there is no glassy-vs-rubbery terminal stage name; `regime` is resolved against final_T_K
    by the shared oracle, exactly as before.
    """
    output_dir = args.output_dir or f'{REPO_ROOT}/data/{args.run_name}/raw/'
    graphs_dir = _run_graphs_dir(args)
    ct_decay = cls.get('ct_min_decay_melt', 0.1) if cls.get('ct_gate_reliable', True) else None
    lammps_base = f'{REPO_ROOT}/data/{args.run_name}/lammps'
    sched = temperature_schedule(args, cls)
    final_T = sched['final_T_K']
    prod = 'npt_final'
    npt_prod_data_path = args.data_path or f'{lammps_base}/cool/{prod}/{prod}_out.data'
    # args.npt_prod_log is never set in real execution; derive the sibling .log of the REAL
    # data path rather than re-deriving a flat convention path that does not exist under the
    # attempt layout (the bug that silently disabled this binding gate on every run once).
    npt_prod_log_path = _derive_npt_prod_log_path(args, npt_prod_data_path, lammps_base)
    return {'output_dir': output_dir, 'graphs_dir': graphs_dir, 'ct_min_decay_melt': ct_decay,
            'cutoff_A': cls.get('cutoff_A'),
            'npt_prod_log_path': npt_prod_log_path,
            'npt_prod_data_path': npt_prod_data_path,
            'melt_dump_path': (args.npt_prod_dump
                               or f'{lammps_base}/cool/nvt_kinetic_stability/'
                                  'nvt_kinetic_stability.dump'),
            'struct_dump_path': (getattr(args, 'struct_dump_path', None)
                                 or f'{lammps_base}/cool/{prod}/{prod}.dump'),
            # The melt reference for assess_cooling_contraction's melt->glass span. Previously
            # this fell back to npt_final_out.data -- the SAME file as glass_data -- so a run
            # whose generator emitted no melt tag silently compared the glass against itself.
            # It is a named stage now, so the fallback is a real and different cell.
            'melt_data_path': (getattr(args, 'melt_data_path', None)
                               or f'{lammps_base}/equil/npt_melt_hold/npt_melt_hold_out.data'),
            # The hot endpoint of the contraction span is where the melt was actually held,
            # not T_workflow_K (which is 300 K for a rubbery class and would misstate the span).
            'T_melt_hold_K': sched['T_melt_hold_K'],
            'npt_prod_temp_K': final_T,
            'T_workflow_K': _resolve_t_workflow(args, cls),
            'exp_tg_point_K': _exp_tg_point(cls, getattr(args, 'smiles', None)),
            # is_glassy derives from the regime oracle rather than re-testing T_workflow > 300:
            # that proxy and _regime would disagree the moment final_T_K is not 300, and this
            # dict feeds both the gate set (regime) and the mechanical routing (is_glassy).
            'is_glassy': _regime(args, cls) == 'glassy',
            'regime': _regime(args, cls),
            'dp': getattr(args, 'dp', None) or cls.get('dp_typical'),
            'ct_gate_reliable': cls.get('ct_gate_reliable', True),
            'backbone_types': args.backbone_types or cls.get('backbone_types'),
            'dt_fs': _pick(args.dt_fs, cls, 'dt_fs', 1.0)}


def _resolve_murnaghan_params(args, cls: dict) -> dict:
    """Resolve deterministic Murnaghan bulk-modulus arguments."""
    lammps_base = f'{REPO_ROOT}/data/{args.run_name}/lammps'
    sampling_factor = int(cls.get('mechanical_sampling_factor', 1))
    is_glassy = _is_glassy(args, cls)
    # args.data_path IS the equilibration attempt's real npt_prod_data_path in real execution
    # (run_campaign.py sets it from the accepted equilibration manifest before this resolver
    # runs); the fallback below is a --dry-run-only preview default. npt_final is unconditionally
    # the terminal stage in the 8-stage adaptive protocol (regardless of regime -- cool_block
    # always ramps down to final_T_K), so no glassy/rubbery branch is needed anymore.
    default_equil_data = f'{lammps_base}/cool/npt_final/npt_final_out.data'
    equil_data_path = args.data_path or default_equil_data
    npt_prod_log_path = _derive_npt_prod_log_path(args, equil_data_path, lammps_base)
    return {'lammps_flags': _lammps_flags(args.lammps_flags, cls), 'work_dir': args.work_dir or f'{REPO_ROOT}/data/{args.run_name}/lammps/mechanical', 'is_glassy': is_glassy, 'bm_pressures_atm': cls.get('mechanical_resample_points') or cls.get('bm_pressures_atm', None), 'dt_fs': _pick(args.dt_fs, cls, 'dt_fs', 1.0), 'cutoff_A': cls.get('cutoff_A'), 'use_long_range': cls.get('electrostatics', 'pppm') == 'pppm', 'equil_data_path': equil_data_path, 'npt_prod_log_path': npt_prod_log_path, 'temp_K': cls.get('bm_temperature_K', 300.0), 'npt_steps': int(cls.get('bm_npt_steps', 500000)) * sampling_factor, 'thermo_freq': int(cls.get('bm_thermo_freq', 100)), 'thermostat_damp_fs': cls.get('thermostat_damp_fs', 100.0), 'barostat_damp_fs': cls.get('barostat_damp_fs', 1000.0), 'mechanical_sampling_factor': sampling_factor, 'bm_per_point_max_extensions': int(cls.get('bm_per_point_max_extensions', 2)), 'bm_per_point_stability_pct': cls.get('bm_per_point_stability_pct', 1.0), 'bm_per_point_min_n_eff': cls.get('bm_per_point_min_n_eff', 5.0), 'gpu_ids': args.gpu_ids, 'mpi_ranks': args.mpi_ranks, 'engine': args.engine, 'velocity_seed': _velocity_seed(args)}

def _resolve_analyze_bm_params(args, cls: dict) -> dict:
    """Resolve deterministic bulk-modulus extraction arguments."""
    output_dir = args.output_dir or f'{REPO_ROOT}/data/{args.run_name}/raw/'
    graphs_dir = _run_graphs_dir(args)
    lammps_base = f'{REPO_ROOT}/data/{args.run_name}/lammps'
    _k_from_cls = _exp_K_range(cls)
    exp_K = [args.exp_K_min if args.exp_K_min is not None else _k_from_cls[0], args.exp_K_max if args.exp_K_max is not None else _k_from_cls[1]]
    K_deform_rate_slow_inv_s = cls.get('K_deform_rate_slow_inv_s', None)
    # Same bug and fix as _resolve_equil_check_params: args.npt_prod_log is never set in real
    # execution, so this always fell to a nonexistent flat-convention path -- silently disabling
    # the fluctuation cross-check (PE1's real bulk_modulus_murnaghan.json carried
    # fluctuation_bulk_modulus_GPa=null, 2026-08-17). args.data_path IS the equilibration
    # attempt's real npt_prod_data_path here (the mechanical stage's dependency mapping sets it
    # from the accepted equilibration manifest) -- derive the sibling .log the same way.
    npt_prod_log_path = _derive_npt_prod_log_path(args, args.data_path, lammps_base)
    return {'output_dir': output_dir, 'graphs_dir': graphs_dir, 'npt_prod_log_path': npt_prod_log_path, 'exp_K_range': exp_K, 'bm_pressures_atm': cls.get('bm_pressures_atm', None), 'strain_rate_per_fs': cls.get('K_deform_rate_inv_s', 100000000.0) * 1e-15, 'strain_rate_slow_per_fs': K_deform_rate_slow_inv_s * 1e-15 if K_deform_rate_slow_inv_s is not None else None, 'K_strain_max': cls.get('K_strain_max', 0.03), 'deform_eq_steps': int(cls.get('deform_eq_steps', 200000)), 'deform_strain_start': cls.get('deform_strain_start', 0.002), 'deform_avg_window': int(cls.get('deform_avg_window', 2000)), 'deform_log_path': getattr(args, 'deform_log', None), 'deform_log_path_slow': getattr(args, 'deform_log_slow', None), 'murnaghan_log_files': getattr(args, 'murnaghan_logs', None), 'dt_fs': _pick(args.dt_fs, cls, 'dt_fs', 1.0)}

def _resolve_run_summary_params(args, cls: dict) -> dict:
    """Resolve deterministic run-summary arguments.

    Every field is derived from CLI flags + the (plan-overlaid) class defaults + the
    deterministic output_dir convention — NOT from the plan's decisions[] list or the --plan
    path — so a deterministic plan still produces byte-identical output to the no-plan path
    The plan provenance is carried by reading raw/run_plan.json at the convention path below.
    """
    # No experimental comparison here -- most runs are novel systems with no curated
    # experimental reference, so a PASS/FAIL grading column would be blank far more often than
    # not. See db/query_best_match.py's exp_lookup.json (written separately, for provenance)
    # for a human to compare against literature by hand when a reference happens to exist.
    output_dir = args.output_dir or f'{REPO_ROOT}/data/{args.run_name}/raw/'
    graphs_dir = _run_graphs_dir(args)
    run_plan = f"{output_dir.rstrip('/')}/run_plan.json"
    dp = args.dp if args.dp is not None else cls.get('dp_typical')
    nchain = args.nchain if args.nchain is not None else cls.get('nchain')
    charge_method = args.charge_method or cls.get('charge_method')
    ff = args.ff or cls.get('preferred_ff', 'pcff')
    d01 = args.d01 or ff
    d02 = args.d02 or charge_method
    d03 = args.d03 or cls.get('electrostatics')
    d04 = args.d04 or (f'DP={dp}, {nchain} chains' if dp and nchain else None)
    return {'output_dir': output_dir, 'graphs_dir': graphs_dir, 'run_plan': run_plan, 'dp': dp, 'nchain': nchain, 'charge_method': charge_method, 'ff': ff, 'd01_ff': d01, 'd02_charges': d02, 'd03_electrostatics': d03, 'd04_system_size': d04}
_STAGE_RESOLVERS = {'build': _resolve_build_params, 'equil': _resolve_equil_params, 'cool': _resolve_cool_params, 'cool-check': _resolve_cool_check_params, 'tg': _resolve_tg_params, 'deform': _resolve_deform_params, 'analyze-tg': _resolve_analyze_tg_params, 'equil-check': _resolve_equil_check_params, 'murnaghan': _resolve_murnaghan_params, 'analyze-bm': _resolve_analyze_bm_params, 'run-summary': _resolve_run_summary_params}

def resolve_stage_params(stage: str, args, cls: dict) -> dict:
    """Resolve routing and physics decisions into concrete tool arguments."""
    resolver = _STAGE_RESOLVERS.get(stage)
    if resolver is None:
        raise ValueError(f'resolve_stage_params: no resolver for stage {stage!r} (valid: {sorted(_STAGE_RESOLVERS)})')
    return resolver(args, cls)
