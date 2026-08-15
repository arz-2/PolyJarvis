#!/usr/bin/env python3
"""
gen_prompt.py — Generate fully-formed worker prompts for PolyJarvis orchestrator.

Usage:
  python3 orchestration/gen_prompt.py --stage <STAGE> [options]

Workers: build | equil | tg | deform | murnaghan | analyze-tg | equil-check | analyze-bm | run-summary

The script reads polymer_rules.json (for class defaults) at runtime, so prompts
always reflect the current configuration without the orchestrator needing to
read it directly.

Required for all workers:
  --run_name NAME
  --polymer_class CLASS   (e.g. PSTR, PACR, PHYC)

Optional overrides (defaults come from polymer_rules.json):
  --smiles SMILES
  --data_path PATH        input .data file (equil, tg, deform, analyze)
  --work_dir PATH         base directory for worker outputs
  --gpu_ids IDS           comma-separated GPU IDs, e.g. "0" or "0,1"; if omitted,
                          derived from polymer_rules.json hardware_policy by FF
  --mpi_ranks N           MPI processes per run; if omitted, derived from
                          hardware_policy (never mpi=1 for PPPM classes)
  --dp N                  degree of polymerisation override
  --nchain N              number of chains override
  --lammps_flags JSON     e.g. '{"use_pcff":true,"use_opls":false}'
  --is_glassy BOOL        true|false (deform, murnaghan). Omitted → derived from T_workflow.
  --tg_k FLOAT            Tg in K (from tg-analysis-worker RESULT)
  --tg_fit_quality STR    Tg fit quality (run-summary + analyze-bm)
  --deform_log PATH       npt_deform log (analyze-bm, glassy deform fallback)
  --murnaghan_logs JSON   JSON list of log paths (analyze-bm, rubbery+pressures path)
  --d05 STR               equil_verdict from equil-checker RESULT (run-summary worker)
  --npt_prod_log PATH     NPT production log (equil-check, analyze-bm)
  --npt_prod_dump PATH    structural-check dump override (equil-check); defaults to the
                          melt nvt_production.dump — NOT the production NPT dump
  --ff STR                force field string (run-summary, analyze-bm)
  --backbone_types JSON   atom type IDs as JSON list (equil-check, analyze-tg)
  --enthalpy_col STR      LAMMPS thermo column name for enthalpy (analyze-tg; default "Enthalpy")
  --output_dir PATH       raw/ output directory

Physics knob overrides (all optional; defaults from polymer_rules.json):
  --npt_prod_ns FLOAT     NPT production time in ns (equil). Auto-sized by
                          atom count when omitted. Converted to npt_prod_steps and
                          passed to generate_equilibration_workflow.
  --npt_cool_steps INT    Override npt_cool step count (default: atom-count tier).
                          re_melt_slow_recool lever — larger = slower cool ramp.
  --npt_cool300_steps INT Override npt_cool300 step count (default: ~1ns, glassy only).
                          re_melt_slow_recool lever — larger = slower cool to 300K.
  --T_equil_K FLOAT       Equilibration temperature — maps to temp= in generate_equilibration_workflow
  --T_anneal_high_K FLOAT Peak annealing temperature — maps to max_temp=
  --tg_t_high_K FLOAT     Tg sweep start temperature (K)
  --tg_t_low_K FLOAT      Tg sweep end temperature (K)
  --tg_t_step_K FLOAT     Tg sweep temperature step (K); halve for BORDERLINE recovery
  --tg_steps_per_t INT    MD steps per temperature window; rejected with --tg_rate_index,
                          which derives it from the rate
  --bm_npt_steps INT      MD steps per Murnaghan pressure point (default 500000)
  --K_strain_max FLOAT    Max engineering strain for uniaxial deformation
  --K_deform_rate_inv_s FLOAT  Engineering strain rate (s⁻¹)
  --dt_fs FLOAT           MD timestep (fs); set 0.5 for "lost atoms" recovery
  --properties LIST       Comma-separated: density,tg,bulk_modulus or 'all' (default).
                          Orchestrator uses it for track gating.
"""

import argparse
import hashlib
import json
import os
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import (load_rules, resolve_ff_family,  # shared rules/FF-family access
                       get_class_entry, host_matches, live_host)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RULES_PATH = REPO_ROOT / "guides" / "polymer_rules.json"

# Appended to every prompt (see main()) — agent-memory writes resolve relative to Bash cwd.
CWD_NOTE = (
    "\n\n---\n**Bash cwd:** never `cd`; use absolute paths. Your "
    "`.claude/agent-memory/<worker>/` notes resolve relative to cwd — `cd` strands "
    "them outside the repo root."
)

WORKER_GUIDES = {
    "build":        "MOLECULE_BUILDER.md",
    "equil":        "EQUILIBRATION.md",
    "tg":           "THERMAL_SWEEP.md",
    "analyze-tg":   "THERMAL_ANALYSIS.md",
    "analyze-tg-multirate": "THERMAL_ANALYSIS.md",
    "equil-check":  "EQUIL_CHECK.md",
    "analyze-bm":   "BM_ANALYSIS.md",
    "deform":       "DEFORM.md",
    "murnaghan":    "MURNAGHAN.md",
    "run-summary":  None,
}


# ─── Loaders ──────────────────────────────────────────────────────────────────
# load_rules() is imported from hw_common (single source of truth).

def load_worker_guide(stage: str) -> str:
    filename = WORKER_GUIDES.get(stage)
    if not filename:
        return ""
    path = REPO_ROOT / "guides" / filename
    return path.read_text() if path.exists() else f"[Guide not found: {filename}]"


def load_plan(plan_path: str) -> dict:
    with open(plan_path) as f:
        return json.load(f)


def apply_plan(cls: dict, plan: dict, args) -> dict:
    """Overlay an approved run_plan.json's decided_params onto the class entry.

    The plan carries the Planner's *scientific decisions* (FF, system size, T-schedule,
    property knobs); runtime wiring (paths, gpu_ids, mpi_ranks) stays in CLI args. For a
    deterministic plan, decided_params is a subset of cls with identical values, so this
    overlay is an identity and worker prompts are byte-identical to the no-plan path
    (enforced by tests/test_plan_reproducibility.py). For a reasoned plan, decided_params
    may differ and those values take effect here.

    Also backfills --smiles and --properties from the plan when not given on the CLI, so
    the plan artifact is a self-contained source of truth.
    """
    effective = {**cls, **plan.get("decided_params", {})}
    if args.smiles is None and plan.get("smiles"):
        args.smiles = plan["smiles"]
    if (args.properties is None or args.properties == "all") and plan.get("properties"):
        args.properties = ",".join(plan["properties"])
    _apply_plan_hardware(args, plan.get("decided_params", {}))
    return effective


def _apply_plan_hardware(args, dp: dict) -> None:
    """Honor a reasoned plan's D-08_hardware override (engine / gpu_per_run / mpi_ranks in
    decided_params) when the CLI omitted the value. Precedence: CLI > plan > policy — the CLI
    stays authoritative, and resolve_hardware() fills anything still unset from hardware_policy.
    Deterministic plans never carry these keys (make_deterministic_plan.SNAPSHOT_KEYS excludes
    them), so the no-plan path stays byte-identical (tests/test_plan_reproducibility.py)."""
    if args.mpi_ranks is None and dp.get("mpi_ranks") is not None:
        args.mpi_ranks = dp["mpi_ranks"]
    if getattr(args, "engine", None) is None and dp.get("engine") is not None:
        args.engine = dp["engine"]          # plan's D-08 engine (gpu | kokkos | cpu)
    if args.gpu_ids is None and ("engine" in dp or "gpu_per_run" in dp):
        engine, gpu_n = dp.get("engine"), dp.get("gpu_per_run")
        if engine == "cpu" or gpu_n == 0:
            args.gpu_ids = ""                                  # CPU engine — hide GPUs
        elif gpu_n:                                            # explicit GPU count → placeholders
            args.gpu_ids = ",".join(str(i) for i in range(int(gpu_n)))
        # engine=="gpu" with no count → leave None; resolve_hardware fills from gpu_per_run policy
    # Fixed seeds for replication runs (deterministic plans pin these from REVISION_PARAMS.md).
    if getattr(args, "emc_seed", None) is None and dp.get("emc_seed") is not None:
        args.emc_seed = dp["emc_seed"]
    if getattr(args, "velocity_seed", None) is None and dp.get("velocity_seed") is not None:
        args.velocity_seed = dp["velocity_seed"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def resolve_hardware(args, cls: dict, rules: dict) -> None:
    """Fill mpi_ranks / gpu_ids from the FF×size hardware_policy when the CLI omits
    them, so a run can never default to the mpi=1 anti-pattern. Explicit CLI values
    always win (keeps deterministic-plan output byte-identical — runtime wiring stays
    CLI-authoritative per apply_plan's contract). Specific gpu_ids remain runtime;
    use orchestration/pick_gpu.py to claim a non-colliding GPU at submit time."""
    hp = rules.get("hardware_policy")
    if not hp:
        return
    # Fresh-clone nudge: the per-FF engine defaults below were benchmarked on hp.host and
    # the crossover is hardware-dependent (KOKKOS wins PPPM but loses small UA cells on this
    # GPU; another GPU/core-count can flip it). If this box isn't the benchmarked one — or no
    # clean sweep has run here — the defaults are directional, not measured-for-you. Advisory
    # only: resolution proceeds unchanged (defaults still apply at D-08 confidence:low).
    if not hp.get("values_are_benchmarked") or not host_matches(rules):
        saved = hp.get("host") or {}
        saved_desc = (f"{saved.get('gpus','?')}x {saved.get('gpu_model','?')} / "
                      f"{saved.get('phys_cores','?')} cores" if saved else "(never calibrated)")
        live = live_host()
        live_desc = f"{live['gpus']}x {live['gpu_model']} / {live['phys_cores']} cores"
        print(f"INFO: hardware_policy was benchmarked on {saved_desc}; you are on {live_desc} "
              f"(values_are_benchmarked={hp.get('values_are_benchmarked', False)}). Run "
              f"/calibrate-hardware once to host-match the per-FF engine defaults.",
              file=sys.stderr)
    ff_raw = cls.get("preferred_ff") or cls.get("forcefield") or ""
    fam = resolve_ff_family(ff_raw, hp)
    pol = hp.get("by_forcefield", {}).get(fam, {})
    # Resolve the launch engine the worker forwards to the MCP run tools. Precedence:
    # CLI/plan (already on args) > policy by_forcefield[fam].engine > "gpu". Only "kokkos" opts
    # into full-offload; "cpu"/anything else normalizes to "gpu" so chain launches stay as today
    # (per-stage use_gpu still governs CPU-only stages inside the deck).
    if getattr(args, "engine", None) is None:
        args.engine = pol.get("engine")
    if args.engine != "kokkos":
        args.engine = "gpu"
    if args.mpi_ranks is None:
        args.mpi_ranks = pol.get("mpi", 8)
        print(f"INFO: mpi_ranks not given — derived {args.mpi_ranks} from "
              f"hardware_policy[{fam}] (engine={pol.get('engine')})", file=sys.stderr)
    if args.gpu_ids is None:
        if pol.get("engine") == "cpu":
            args.gpu_ids = ""
        else:
            # emit gpu_per_run placeholder ids (e.g. "0,1" for a 2-GPU run); the orchestrator
            # claims that many free GPUs via orchestration/pick_gpu.py claim --need N at submit time.
            n = max(1, int(pol.get("gpu_per_run", 1) or 1))
            args.gpu_ids = ",".join(str(i) for i in range(n))
        print(f"INFO: gpu_ids not given — derived \"{args.gpu_ids}\" from "
              f"hardware_policy[{fam}]; claim free GPU(s) with orchestration/pick_gpu.py",
              file=sys.stderr)


def _v(val, fallback="<FILL>"):
    return val if val is not None else fallback


def _pick(arg_val, cls: dict, key: str, default):
    """CLI flag takes precedence over polymer_rules.json; rules over hard default."""
    return arg_val if arg_val is not None else cls.get(key, default)


def _lammps_flags(flags_json: str | None, cls: dict) -> dict:
    if flags_json:
        return json.loads(flags_json)
    ff = cls.get("preferred_ff", "").lower()
    # Substring/family match (mutually exclusive tokens) — an exact-match here returned
    # use_opls=False for both PHAL and PSIL, whose canonical field is "opls/2024/opls-aa".
    # compass is class2 like pcff but shares no token with it, so it must be named: the
    # substring chain alone returns all-False and the deck falls back to GAFF2 styles
    # (lj/charmm/coul/long, mix arithmetic) against a class2 params file.
    # Mirrors mcp-emc-server's own _lammps_flags field grouping.
    class_ii = ("pcff" in ff) or ff in ("compass", "pcff_ore")
    return {
        "use_pcff": class_ii,
        "use_opls": "opls" in ff,
        "use_trappe": "trappe" in ff,
    }


def _exp_tg_range(cls: dict, run_name: str | None = None) -> list:
    tg = cls.get("experimental_tg_K")
    if isinstance(tg, dict):
        if run_name:
            for key, val in tg.items():
                if isinstance(val, (int, float)) and run_name.upper().startswith(key.upper()):
                    return [round(val - 20), round(val + 20)]
        vals = sorted(v for v in tg.values() if isinstance(v, (int, float)))
        if vals:
            mid = vals[len(vals) // 2]
            return [round(mid - 20), round(mid + 20)]
    if isinstance(tg, (int, float)):
        return [round(tg - 20), round(tg + 20)]
    return ["<exp_tg_min>", "<exp_tg_max>"]


def _melt_reference_db_name(cls: dict, run_name: str | None = None):
    """Exact DB polymer name for THIS run's member, for the melt-density gate, or None.

    Without it the lookup falls back to the class representative, which is a different
    polymer for any run that is not the flagship member — POXI's representative is
    polyoxymethylene while a PEO/PEG run belongs against polyoxyethylene (18% denser),
    PVNL's is PVC against PVAc (16%), PHAL's is PTFE against PVDF (6%). Grading a correct
    cell against the wrong polymer manufactures a STRUCTURAL_FAIL. Longest key first so
    'Nylon-66' wins over a hypothetical 'Nylon-6' prefix.
    """
    names = cls.get("melt_reference_db_names") or {}
    if not names or not run_name:
        return None
    for member in sorted(names, key=len, reverse=True):
        if run_name.upper().startswith(member.upper()):
            return names[member]
    return None


def _fox_flory_K(cls: dict, run_name: str | None = None):
    """Flory-Fox K for THIS run's member, or None.

    The constant is measured for one polymer, not for a whole class: PACR's 1.4e5 is PMMA's
    and PSTR's 1.083e5 is atactic PS's. Returning the class value unconditionally would give
    a PMA run (exp Tg 281 K) a -32 K band shift from a constant never measured for it —
    a fabricated number inside a PASS/FAIL band, arrived at by misapplication rather than
    invention. Member resolution mirrors _exp_tg_range's run-name prefix match.
    """
    ff = cls.get("tg_fox_flory_K") or {}
    K, members = ff.get("K_K_g_per_mol"), ff.get("members")
    if K is None or not members or not run_name:
        return None
    return K if any(run_name.upper().startswith(m.upper()) for m in members) else None


def _exp_tg_point(cls: dict, run_name: str | None = None):
    """Point exp_tg_K value (not a ±20 band) for assess_cooling_contraction's tg_K arg.
    Mirrors _exp_tg_range's member-resolution logic (fixes the class-mean-averaging bug
    for multi-member classes — see memory feedback_genprompt_exp_tg_avg_bug.md)."""
    tg = cls.get("experimental_tg_K")
    if isinstance(tg, dict):
        if run_name:
            for key, val in tg.items():
                if isinstance(val, (int, float)) and run_name.upper().startswith(key.upper()):
                    return val
        vals = sorted(v for v in tg.values() if isinstance(v, (int, float)))
        return vals[len(vals) // 2] if vals else None
    if isinstance(tg, (int, float)):
        return tg
    return None


def _exp_density_point(cls: dict, run_name: str | None = None):
    """Point exp_density_gcm3 value (not a ±5% band) for assess_cooling_contraction."""
    exp = cls.get("experimental_density_gcm3")
    if isinstance(exp, dict):
        if run_name:
            for key, val in exp.items():
                if isinstance(val, (int, float)) and run_name.upper().startswith(key.upper()):
                    return val
        vals = sorted(v for v in exp.values() if isinstance(v, (int, float)))
        return vals[len(vals) // 2] if vals else None
    if isinstance(exp, (int, float)):
        return exp
    return None


def _exp_K_range(cls: dict) -> list:
    exp = cls.get("exp_K_GPa")
    if isinstance(exp, dict) and "min" in exp and "max" in exp:
        return [exp["min"], exp["max"]]
    return [None, None]


def _db_exp_lookup(cls_id: str, polymer_name: str | None = None) -> dict:
    """Query polymer_db.sqlite for polymer-specific experimental values.

    Priority in callers:
      --exp_tg_K (CLI)  >  this function (DB)  >  polymer_rules.json median
    Returns dict with tg_median_K, density_gcm3, K_range_GPa (any may be None).
    Never raises — a broken or missing DB just returns all-None.
    """
    try:
        import sys as _sys
        _repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if _repo_root not in _sys.path:
            _sys.path.insert(0, _repo_root)
        from db.query_best_match import (
            _connect, find_polymer_ids, get_tg_data, get_density_data, get_bulk_modulus_data,
        )
        conn = _connect()
        ids, _method, _conf = find_polymer_ids(conn, polymer_name, cls_id)
        if not ids:
            return {"tg_median_K": None, "density_gcm3": None, "K_range_GPa": None}
        tg = get_tg_data(conn, ids)
        dens = get_density_data(conn, ids, 300.0)
        bm = get_bulk_modulus_data(conn, ids, is_glassy=True)
        return {
            "tg_median_K": tg["agg_median_K"] if tg else None,
            "density_gcm3": dens.get("value_gcm3") if dens else None,
            "K_range_GPa": bm["agg_range_GPa"] if bm else None,
        }
    except Exception:
        return {"tg_median_K": None, "density_gcm3": None, "K_range_GPa": None}


def _exp_density_range(cls: dict) -> list:
    exp = cls.get("experimental_density_gcm3")
    if isinstance(exp, dict):
        vals = sorted(v for v in exp.values() if isinstance(v, (int, float)))
        if vals:
            mid = vals[len(vals) // 2]  # median — avoids outliers skewing the comparison band
            return [round(mid * 0.95, 3), round(mid * 1.05, 3)]
    if isinstance(exp, (int, float)):
        return [round(exp * 0.95, 3), round(exp * 1.05, 3)]
    # Fallback: derive from density_initial (~0.5–0.6× RT density)
    d0 = cls.get("density_initial_gcm3", 0.6)
    implied_rt = d0 / 0.55
    return [round(implied_rt * 0.85, 3), round(implied_rt * 1.15, 3)]


# ─── Stage prompt builders ────────────────────────────────────────────────────

def _resolve_build_params(args, cls: dict) -> dict:
    """Resolved values for the build stage — consumed by build_prompt's text template and,
    identically, by run_deterministic_replicate.py's scripted molecule-builder call."""
    return {
        "smiles": args.smiles,
        "work_dir": args.work_dir or f"{REPO_ROOT}/data/{args.run_name}/lammps",
        "preferred_builder": cls.get('preferred_builder', 'emc'),
        "preferred_ff": cls.get('preferred_ff', 'gaff2_mod'),
        "dp": args.dp or cls.get('dp_typical', 50),
        "nchain": args.nchain or cls.get('nchain', 10),
        "density_initial_gcm3": _pick(args.density_initial, cls, 'density_initial_gcm3', 0.6),
        "emc_seed": args.emc_seed if getattr(args, 'emc_seed', None) is not None else None,
        "charge_method": cls.get('charge_method', 'am1bcc').lower(),
        "electrostatics": cls.get('electrostatics', 'pppm'),
        "cutoff_A": cls.get('cutoff_A', 12.0),
        "dt_fs": cls.get('dt_fs', 1.0),
        "phal_patch": args.polymer_class.upper() == 'PHAL',
        "lammps_flags": _lammps_flags(args.lammps_flags, cls),
        "ff_confidence": "cited" if cls.get('ff_justification_doi') else "uncited",
    }


def build_prompt(args, cls: dict) -> str:
    p = _resolve_build_params(args, cls)
    guide = load_worker_guide("build")
    return f"""\
smiles:            {_v(p['smiles'])}
run_name:          {args.run_name}
work_dir:          {p['work_dir']}/cell
polymer_class:     {args.polymer_class.upper()}
preferred_builder: {p['preferred_builder']}
preferred_ff:      {p['preferred_ff']}
dp:                {p['dp']}   # submit_emc_cell_job dp= — the 20 default is not this class's dp_typical
nchain:            {p['nchain']}   # submit_emc_cell_job nchains= — default 10
density_initial:   {p['density_initial_gcm3']}   # submit_emc_cell_job density_initial= — default 0.6
emc_seed:          {p['emc_seed'] if p['emc_seed'] is not None else 'null'}   # submit_emc_cell_job seed= — null here means DRAW an integer yourself and pass it; never seed=-1 (irreproducible, and the guide forbids it). get_emc_job_output echoes it as resolved_seed; report that integer so the run log's Seeds line is both real and reproducible
charge_method:     {p['charge_method']}
electrostatics:    {p['electrostatics']}
cutoff_A:          {p['cutoff_A']}   # downstream LAMMPS deck only — submit_emc_cell_job has no cutoff argument
dt_fs:             {p['dt_fs']}   # downstream LAMMPS deck only — submit_emc_cell_job has no timestep argument
phal_patch:        {str(p['phal_patch']).lower()}
ff_confidence:     {p['ff_confidence']}

Every field annotated `submit_emc_cell_job <arg>=` is an argument of that tool. Pass each one on
the call. Omitting an argument is a schema error, not a default.

--- Worker Guide (MOLECULE_BUILDER) ---
{guide}
"""


def _resolve_t_workflow(args, cls: dict) -> float:
    """Equilibration workflow temperature (K). Plan's T_workflow_K wins; otherwise 300 K for
    rubbery (exp_Tg < 300) and T_equil_K for glassy. Mirrors generate_equilibration_workflow,
    whose chain ends at npt_production when T ≤ 300 (rubbery, 7-run) and appends npt_prod300
    when T > 300 (glassy, 9-run)."""
    exp_tg_override = getattr(args, 'exp_tg_K', None)
    if exp_tg_override is not None:
        exp_tg = exp_tg_override
    else:
        _tg_dict = cls.get('experimental_tg_K')
        if isinstance(_tg_dict, dict):
            _run = getattr(args, 'run_name', None)
            exp_tg = None
            if _run:
                for k, v in _tg_dict.items():
                    if isinstance(v, (int, float)) and _run.upper().startswith(k.upper()):
                        exp_tg = v
                        break
            if exp_tg is None:
                _vals = sorted(v for v in _tg_dict.values() if isinstance(v, (int, float)))
                exp_tg = _vals[len(_vals) // 2] if _vals else None
        else:
            exp_tg = _tg_dict
    if "T_workflow_K" in cls:
        return cls["T_workflow_K"]
    T_equil = _pick(getattr(args, 'T_equil_K', None), cls, 'T_equil_K', 600.0)
    return 300.0 if isinstance(exp_tg, (int, float)) and exp_tg < 300 else T_equil


def _regime(args, cls: dict) -> str:
    """Single regime oracle: 'rubbery' if the workflow produces above Tg, else 'glassy'.

    Defined as T_workflow ≤ 300 K (⇔ exp_Tg < 300, via _resolve_t_workflow) so it agrees by
    construction with which equilibration chain was built (rubbery = 7-run ending at
    npt_production; glassy = 9-run with npt_prod300) and with the property-track routing.
    Consumed by the equil-check carve-out (require_rubbery), the analyze-tg data path, the
    multirate slope-gate exemption, and rubbery-K routing — one definition, fed everywhere.
    NOTE: do NOT redefine as `T_workflow > exp_Tg + margin`; for a glassy polymer T_workflow is
    the melt-equilibration temperature (~T_equil), which would mis-label glassy melts as rubbery."""
    return "rubbery" if _resolve_t_workflow(args, cls) <= 300.0 else "glassy"


def _is_glassy(args, cls: dict) -> bool:
    """Whether the BM stages treat this cell as glassy. The orchestrator's `--is_glassy`, set from
    the thermal track's measured Tg, wins; with the flag absent the regime oracle decides. An
    argparse default cannot: it applies to every class alike, so a rubbery run silently reads as
    glassy and takes the Murnaghan/deform glassy branch."""
    flag = getattr(args, 'is_glassy', None)
    if flag is not None:
        return str(flag).lower() not in ("false", "0", "no")
    return _regime(args, cls) == "glassy"


def _velocity_seed(args) -> int:
    """The equilibration chain's `velocity all create` seed. generate_equilibration_workflow
    rejects a null seed, so resolve one here: the plan's pinned value if it has one, else a
    value derived from run_name — stable across prompt regenerations, distinct per replicate."""
    pinned = getattr(args, 'velocity_seed', None)
    if pinned is not None:
        return int(pinned)
    digest = hashlib.sha256(args.run_name.encode()).hexdigest()
    return 10000 + int(digest, 16) % 989_999


def _resolve_equil_params(args, cls: dict) -> dict:
    """Resolved values for the equilibration stage — consumed by equil_prompt's text template
    and, identically, by run_deterministic_replicate.py's scripted equilibration-chain call."""
    dt = _pick(args.dt_fs, cls, 'dt_fs', 1.0)
    T_equil = _pick(args.T_equil_K, cls, 'T_equil_K', 600.0)
    npt_prod_ns_val = _pick(args.npt_prod_ns, cls, 'npt_prod_ns', None)
    npt_prod_steps = int(npt_prod_ns_val * 1e6 / dt) if npt_prod_ns_val is not None else None
    T_workflow = _resolve_t_workflow(args, cls)
    add_melt_npt = getattr(args, 'add_melt_npt', False) or (T_workflow <= 300.0)
    melt_npt_ns_val = _pick(None, cls, 'melt_npt_ns', None) if add_melt_npt else None
    melt_npt_steps = (int(melt_npt_ns_val * 1e6 / dt)
                       if (add_melt_npt and melt_npt_ns_val is not None) else None)
    # melt/cooldown split only exists for glassy chains (T_workflow > 300, npt_cool300+
    # npt_prod300 appended) — rubbery already ends at npt_production with nothing to split,
    # so force phase=full regardless of what was passed (prevents an orchestrator mistake from
    # silently truncating a rubbery chain).
    phase = getattr(args, 'phase', 'full') or 'full'
    if T_workflow <= 300.0:
        phase = 'full'
    return {
        "data_path": args.data_path,
        "phase": phase,
        "pending_cooldown_path": getattr(args, 'pending_cooldown_path', None),
        "lammps_flags": _lammps_flags(args.lammps_flags, cls),
        "work_dir": args.work_dir or f"{REPO_ROOT}/data/{args.run_name}/lammps/equil",
        "dt_fs": dt,
        "T_equil_K": T_equil,
        "T_anneal_high_K": _pick(args.T_anneal_high_K, cls, 'annealing_T_high_K', 700.0),
        "T_workflow_K": T_workflow,
        "P_equil_atm": cls.get('P_equil_atm', 1.0),
        "t_equil_ns": cls.get('t_equil_ns', 5.0),
        "npt_cool_steps": _pick(getattr(args, 'npt_cool_steps', None), cls, 'npt_cool_steps', None),
        "npt_cool300_steps": _pick(getattr(args, 'npt_cool300_steps', None), cls, 'npt_cool300_steps', None),
        "npt_prod_ns": npt_prod_ns_val,
        "npt_prod_steps": npt_prod_steps,
        "add_melt_npt": add_melt_npt,
        "melt_npt_ns": melt_npt_ns_val,
        "melt_npt_steps": melt_npt_steps,
        "gpu_ids": args.gpu_ids,
        "mpi_ranks": args.mpi_ranks,
        "engine": args.engine,
        "velocity_seed": _velocity_seed(args),
        # Arms inspect_data_file's pre-submission finite-size forecast: predicted compressed
        # box vs 2*cutoff_A and 2*Rg, so a too-small cell is caught before any GPU time.
        "cutoff_A": cls.get('cutoff_A', 12.0),
        "nchain": args.nchain or cls.get('nchain', 10),
        "exp_density_gcm3": _exp_density_point(cls, args.run_name),
    }


def equil_prompt(args, cls: dict) -> str:
    p = _resolve_equil_params(args, cls)
    guide = load_worker_guide("equil")
    if p["npt_prod_ns"] is not None:
        npt_prod_line = (
            f"t_npt_prod_ns:     {p['npt_prod_ns']}\n"
            f"npt_prod_steps:    {p['npt_prod_steps']}  # pass as npt_prod_steps="
        )
    else:
        npt_prod_line = (
            "t_npt_prod_ns:     null\n"
            "npt_prod_steps:    null  # pass as npt_prod_steps=None — null = atom-count-tier default"
        )
    if p["add_melt_npt"] and p["melt_npt_ns"] is not None:
        melt_npt_line = (
            f"add_melt_npt:      true\n"
            f"t_equil_K:         {p['T_equil_K']}\n"
            f"melt_npt_ns:       {p['melt_npt_ns']}\n"
            f"melt_npt_steps:    {p['melt_npt_steps']}  # pass as melt_npt_steps="
        )
    elif p["add_melt_npt"]:
        melt_npt_line = (
            f"add_melt_npt:      true\n"
            f"t_equil_K:         {p['T_equil_K']}\n"
            f"melt_npt_steps:    null  # pass as melt_npt_steps=None — null = ~1ns default"
        )
    else:
        melt_npt_line = (
            "add_melt_npt:      false\n"
            "melt_npt_steps:    null  # pass as melt_npt_steps=None — unused when add_melt_npt=false"
        )
    cool_steps_line = (
        f"npt_cool_steps:    {_v(p['npt_cool_steps'], 'null')}  # pass as npt_cool_steps= — override, null = atom-count-tier default\n"
        f"npt_cool300_steps: {_v(p['npt_cool300_steps'], 'null')}  # pass as npt_cool300_steps= — override, null = ~1ns default"
    )
    if p["phase"] == "melt":
        phase_line = (
            "phase:             melt   # submit only through npt_production; save the "
            "npt_cool300/npt_prod300 tail to _pending_cooldown_stages.json — do NOT submit it yet"
        )
    elif p["phase"] == "cooldown":
        phase_line = (
            f"phase:             cooldown   # read back {_v(p['pending_cooldown_path'])} and "
            "submit that stage list directly — do NOT call generate_equilibration_workflow again"
        )
    else:
        phase_line = "phase:             full   # single submission, all stages (today's behavior)"
    return f"""\
data_path:         {_v(p['data_path'])}
{phase_line}
lammps_flags:      {json.dumps(p['lammps_flags'])}
run_name:          {args.run_name}
work_dir:          {p['work_dir']}
polymer_class:     {args.polymer_class.upper()}
cutoff_A:          {p['cutoff_A']}   # inspect_data_file lj_cutoff=
nchain:            {p['nchain']}   # inspect_data_file nchain=
exp_density_gcm3:  {p['exp_density_gcm3'] if p['exp_density_gcm3'] is not None else 'null'}   # inspect_data_file target_density_gcm3= — arms the pre-submission size forecast; a SIZE_* error there means REBUILD, do not submit
T_equil_K:         {p['T_equil_K']}
T_workflow_K:      {p['T_workflow_K']}   # pass as temp=
P_equil_atm:       {p['P_equil_atm']}
t_equil_ns:        {p['t_equil_ns']}
T_anneal_high_K:   {p['T_anneal_high_K']}
{cool_steps_line}
dt_fs:             {p['dt_fs']}
{npt_prod_line}
{melt_npt_line}
gpu_ids:           "{p['gpu_ids']}"
mpi_ranks:         {p['mpi_ranks']}
engine:            "{p['engine']}"
velocity_seed:     {p['velocity_seed']}   # pass as velocity_seed= — required, never null
extend_steps:      null   # pass as extend_steps=None — required; only extend_only=True calls set it

Every step count above and velocity_seed are REQUIRED arguments of
generate_equilibration_workflow. Pass each one on the call, including the ones whose value is
null. Omitting an argument is a schema error, not a default.

--- Worker Guide (EQUILIBRATION) ---
{guide}
"""


def _resolve_tg_rate(args, cls: dict):
    """Resolve the selected cooling rate + a per-rate output-dir suffix for multi-rate
    Tg sweeps. Returns (selected_rate | None, rate_suffix). When --tg_rate_index is unset,
    suffix is "" so the single-rate path stays byte-identical to the legacy pipeline."""
    tg_rates = cls.get('tg_rates_K_per_ns', [])
    rate_idx = getattr(args, 'tg_rate_index', None)
    if rate_idx is not None and tg_rates and rate_idx < len(tg_rates):
        selected_rate = tg_rates[rate_idx]
        return selected_rate, f"_r{int(selected_rate)}"
    return None, ""


def _resolve_tg_params(args, cls: dict) -> dict:
    """Resolved values for a single-rate Tg sweep stage — consumed by tg_prompt's text
    template and, identically, by run_deterministic_replicate.py's scripted Tg-sweep call."""
    dt = _pick(args.dt_fs, cls, 'dt_fs', 1.0)
    tg_rates = cls.get('tg_rates_K_per_ns', [])
    rate_idx = getattr(args, 'tg_rate_index', None)
    selected_rate, rate_suffix = _resolve_tg_rate(args, cls)
    t_step = _pick(args.tg_t_step_K, cls, 'tg_t_step_K', 20)
    floor = cls.get('tg_min_steps_per_T', 200000)
    if selected_rate is not None:
        # rate = T_step / (n_steps * dt * 1e-6)
        # In a staircase deck the rate IS the steps/T knob, so --tg_steps_per_t is silently
        # replaced here -- and every thermal-track sweep passes --tg_rate_index. A recovery
        # that "doubles tg_steps_per_t" would rebuild a byte-identical deck, so refuse the
        # pair rather than ignore one half of it. validate_run_plan's OVERRIDDEN_PARAMS
        # reports the same conflict for a plan that records both.
        if getattr(args, 'tg_steps_per_t', None) is not None:
            raise SystemExit(
                f"ERROR: --tg_steps_per_t={args.tg_steps_per_t} is ignored when --tg_rate_index "
                f"selects a rate ({selected_rate} K/ns): the staircase deck derives "
                f"N = tg_t_step_K/(rate*dt) = {int(t_step / (selected_rate * dt * 1e-6))} steps/T. "
                "To change time-per-T, change the rate (--tg_rate_index, or the plan's "
                "tg_rates_K_per_ns); to change resolution, change --tg_t_step_K.")
        n_steps_per_t = int(t_step / (selected_rate * dt * 1e-6))
    else:
        n_steps_per_t = _pick(args.tg_steps_per_t, cls, 'tg_steps_per_t', 500000)
    work_dir = args.work_dir or f"{REPO_ROOT}/data/{args.run_name}/lammps/thermal"
    # The deck's `include` line. THERMAL_SWEEP.md used to hardcode "<work_dir>/emc_build.params",
    # which generate_script passes through verbatim -- and the tg work_dir is a directory no stage
    # ever writes a params copy into (the copies live in cell/ and equil/), so every EMC tg deck
    # failed at parse time. Emit the real path instead. Null on a RadonPy build, where the .data
    # carries its own coefficients and params_file must be omitted.
    _cell_params = Path(f"{REPO_ROOT}/data/{args.run_name}/lammps/cell/emc_build.params")
    return {
        "lammps_flags": _lammps_flags(args.lammps_flags, cls),
        "work_dir": work_dir,
        "emc_params_path": str(_cell_params) if _cell_params.exists() else None,
        "dt_fs": dt,
        "tg_rates_K_per_ns": tg_rates,
        "tg_rate_index": rate_idx,
        "selected_rate_K_per_ns": selected_rate,
        # Per-rate output dir so concurrent/sequential multi-rate sweeps don't collide on
        # one tg_sweep/tg_sweep.log. Single-rate path keeps the legacy "tg_sweep" dir.
        "tg_sweep_dir": f"{work_dir}/tg_sweep{rate_suffix}",
        "T_start_K": _pick(args.tg_t_high_K, cls, 'tg_t_high_K', 600),
        "T_end_K": _pick(args.tg_t_low_K, cls, 'tg_t_low_K', 200),
        "T_step_K": t_step,
        "n_steps_per_t": n_steps_per_t,
        "tg_min_steps_per_T": floor,
        # Backstop only — the plan-time feasibility filter should have rejected an infeasible
        # rate. Never blocking, just flagging: too few ps/T collapses the bilinear Tg fit
        # (cis-PBD2 r400=50ps, PEEK2 r160/r400).
        "below_steps_floor": selected_rate is not None and n_steps_per_t < floor,
        # Rubbery: equil_data_path = npt_tg_prep_data (npt_melt at T_equil_K); Glassy:
        # npt_prod300_out.data. Orchestrator passes the correct cell via --tg_start_data
        # (rubbery) or --data_path (glassy).
        "equil_data_path": getattr(args, 'tg_start_data', None) or args.data_path,
        "gpu_ids": args.gpu_ids,
        "mpi_ranks": args.mpi_ranks,
        "engine": args.engine,
        "velocity_seed": _velocity_seed(args),
    }


def tg_prompt(args, cls: dict) -> str:
    p = _resolve_tg_params(args, cls)
    guide = load_worker_guide("tg")
    tg_floor_warning = ""
    if p["selected_rate_K_per_ns"] is not None:
        rate_line = (
            f"tg_rate_index:     {p['tg_rate_index']}  # rate {p['selected_rate_K_per_ns']} K/ns\n"
            f"  cooling_rate:    {p['selected_rate_K_per_ns']}"
        )
        if p["below_steps_floor"]:
            ps = p["n_steps_per_t"] * p["dt_fs"] * 1e-3
            tg_floor_warning = (
                f"⚠ WARNING: rate {p['selected_rate_K_per_ns']} K/ns → {p['n_steps_per_t']} steps/T = {ps:.0f} ps/T, "
                f"BELOW tg_min_steps_per_T={p['tg_min_steps_per_T']} ({p['tg_min_steps_per_T'] * p['dt_fs'] * 1e-3:.0f} ps). Bilinear Tg fit "
                f"likely DEGENERATE (cis-PBD2/PEEK2 failure mode). This rate is infeasible for "
                f"tg_t_step_K={p['T_step_K']}, dt={p['dt_fs']}fs — investigate fit reliability "
                f"before trusting this value; the plan-time feasibility check "
                f"(_assert_tg_rates_feasible) should have caught this earlier.\n\n"
            )
    else:
        rate_line = f"tg_rate_index:     null  # standard single-rate run"
        if p["tg_rates_K_per_ns"]:
            rate_line += f"\n  all_rates_K_per_ns: {p['tg_rates_K_per_ns']}  # use --tg_rate_index N for multi-rate"

    return f"""\
{tg_floor_warning}equil_data_path:   {_v(p['equil_data_path'])}
lammps_flags:      {json.dumps(p['lammps_flags'])}
polymer_class:     {args.polymer_class.upper()}
run_name:          {args.run_name}
work_dir:          {p['work_dir']}
tg_sweep_dir:      {p['tg_sweep_dir']}
emc_params_path:   {_v(p['emc_params_path'], 'null')}   # generate_script params params_file= — null ⇒ omit params_file entirely (RadonPy cell, coefficients are inline). Never substitute work_dir here; nothing writes a params copy into the thermal dir
tg_params:
  T_start:         {p['T_start_K']}
  T_end:           {p['T_end_K']}
  T_step:          {p['T_step_K']}
  n_steps_per_t:   {p['n_steps_per_t']}
{rate_line}
dt_fs:             {p['dt_fs']}
gpu_ids:           "{p['gpu_ids']}"
mpi_ranks:         {p['mpi_ranks']}
engine:            "{p['engine']}"   # forward as engine= to run_lammps_chain / run_lammps_script / generate_equilibration_workflow
velocity_seed:     {p['velocity_seed']}   # pass as velocity_seed= — required by generate_script, never null
per_t_dump:
  enabled:         true
  file:            {p['tg_sweep_dir']}/per_t_structs.dump   # one final frame per T step
  param_key:       WRITE_PER_T_DUMP=True, PER_T_DUMP_FILE=per_t_structs.dump
  note:            Pass these in generate_script params alongside T_START/T_END/etc.
generate_script:
  template_name:   npt_tg_step   # REQUIRED — the multi-temperature cooling staircase.
  WARNING:         NEVER use template "npt" for a Tg sweep — it renders a single-temperature
                   NPT (no cooling, no per-T dump) and is an invalid sweep.
  required_params: T_START={p['T_start_K']}, T_END={p['T_end_K']}, T_STEP={p['T_step_K']} (map from tg_params above).
                   generate_script RAISES if T_END/T_STEP are missing — verify the rendered .in
                   has a `variable temps index ...` loop before submitting.

--- Worker Guide (THERMAL_SWEEP) ---
{guide}
"""


def _resolve_deform_params(args, cls: dict) -> dict:
    """Resolved values for the deform stage — consumed by deform_prompt's text template and,
    identically, by run_deterministic_replicate.py's scripted deform-fallback call."""
    return {
        "deform_rate_mode": args.deform_rate_mode,
        "equil_data_path": args.data_path,
        "lammps_flags": _lammps_flags(args.lammps_flags, cls),
        "work_dir": args.work_dir or f"{REPO_ROOT}/data/{args.run_name}/lammps/mechanical",
        "is_glassy": _is_glassy(args, cls),
        "K_deform_rate_inv_s": _pick(args.K_deform_rate_inv_s, cls, 'K_deform_rate_inv_s', 1e8),
        "K_deform_rate_slow_inv_s": cls.get('K_deform_rate_slow_inv_s', 'null'),
        "K_strain_max": _pick(args.K_strain_max, cls, 'K_strain_max', 0.03),
        "dt_fs": _pick(args.dt_fs, cls, 'dt_fs', 1.0),
        "gpu_ids": args.gpu_ids,
        "mpi_ranks": args.mpi_ranks,
        "engine": args.engine,
        "velocity_seed": _velocity_seed(args),
    }


def deform_prompt(args, cls: dict) -> str:
    p = _resolve_deform_params(args, cls)
    guide = load_worker_guide("deform")
    return f"""\
deform_rate_mode:  {p['deform_rate_mode']}
equil_data_path:   {_v(p['equil_data_path'])}
lammps_flags:      {json.dumps(p['lammps_flags'])}
polymer_class:     {args.polymer_class.upper()}
run_name:          {args.run_name}
work_dir:          {p['work_dir']}
is_glassy:         {str(p['is_glassy']).lower()}
K_deform_rate_inv_s: {p['K_deform_rate_inv_s']}
K_deform_rate_slow_inv_s: {p['K_deform_rate_slow_inv_s']}
K_strain_max:      {p['K_strain_max']}   # generate_script params STRAIN_MAX=
dt_fs:             {p['dt_fs']}   # generate_script params TIMESTEP=
gpu_ids:           "{p['gpu_ids']}"   # pass as gpu_ids= to run_lammps_script
mpi_ranks:         {p['mpi_ranks']}   # pass as mpi= to run_lammps_script
engine:            "{p['engine']}"   # pass as engine= to run_lammps_script AND in generate_script params — the "gpu" default silently ignores a KOKKOS build
velocity_seed:     {p['velocity_seed']}   # pass as velocity_seed= — required by generate_script, never null

Every field above is an argument of generate_script or run_lammps_script. Pass each one on the
call, including the ones whose value is null. Omitting an argument is a schema error, not a
default.

--- Worker Guide (DEFORM) ---
{guide}
"""


def born_prompt(args, cls: dict) -> str:
    raise SystemExit(
        "ERROR: --stage born is no longer supported. Born+NVT has been removed from the "
        "PolyJarvis pipeline (2026-06-21) due to PCFF+PPPM virial incompatibility (failed "
        "3/3 pipeline runs). Use --stage murnaghan for glassy bulk modulus. "
        "See guides/BM_ANALYSIS.md for the removal rationale."
    )


def _resolve_analyze_tg_params(args, cls: dict) -> dict:
    """Resolved values for the per-rate Tg analysis stage — consumed by analyze_tg_prompt's
    text template and, identically, by run_deterministic_replicate.py's scripted extract_thermal
    call."""
    selected_rate, rate_suffix = _resolve_tg_rate(args, cls)
    # Per-rate analysis dir so the three tg_summary.json files don't overwrite each other.
    # Single-rate (no --tg_rate_index) keeps the legacy raw/ output → reproducibility preserved.
    raw_suffix = f"tg_r{int(selected_rate)}/" if selected_rate is not None else ""
    output_dir = args.output_dir or f"{REPO_ROOT}/data/{args.run_name}/raw/{raw_suffix}"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    lammps_base = f"{REPO_ROOT}/data/{args.run_name}/lammps"
    tg_log = args.data_path or f"{lammps_base}/thermal/tg_sweep{rate_suffix}/tg_sweep.log"
    # equil_data_path: production NPT output — passed to extract_thermal as tg_data_file for ΔCp mass
    # normalisation. Phase-aware: glassy chains end at npt_prod300 (cooled to 300 K); rubbery chains
    # (7-run, since commit 5b640ff) have NO npt_prod300 stage — they end at npt_production at
    # T_equil_K. Defaulting to npt_prod300 on a rubbery chain points at a nonexistent file.
    if _regime(args, cls) == "rubbery":
        default_equil_data = f"{lammps_base}/equil/npt_production/npt_production_out.data"
    else:
        default_equil_data = f"{lammps_base}/equil/npt_prod300/npt_prod300_out.data"
    equil_data = args.equil_data_path or default_equil_data
    # The Tg sweep deck writes one final frame per T step (tg_prompt sets WRITE_PER_T_DUMP=True).
    # extract_thermal's structural block needs per_t_dump_file AND tg_data_file together; without
    # the path the dump is written every run and never read.
    per_t_dump = f"{lammps_base}/thermal/tg_sweep{rate_suffix}/per_t_structs.dump"
    return {
        "selected_rate_K_per_ns": selected_rate,
        "tg_rate_index": args.tg_rate_index,
        "tg_log_path": tg_log,
        "tg_data_file": equil_data,
        "per_t_dump_file": per_t_dump,
        "enthalpy_col": getattr(args, "enthalpy_col", None) or "Enthalpy",
        # Without it the structural block still runs, but every backbone bond vector is dropped and
        # P2 comes back null at every temperature. Same list equil-check already resolved.
        "backbone_types": args.backbone_types or cls.get("backbone_types"),
        "output_dir": output_dir,
        "graphs_dir": graphs_dir,
        # Classes carrying tg_slope_gate_fallback have documented highest-rate degeneracy on the
        # rigid-aromatic staircase (PKTN/PSFO), so their primary-vs-alternative Tg gap routinely
        # exceeds 20 K for a known, already-handled reason. Exempt records the gap without forcing
        # REVIEW -- otherwise the gate fires mostly where the artifact already has a carve-out.
        "method_gap_exempt": bool(cls.get("tg_slope_gate_fallback") == "slowest_rate"),
    }


def analyze_tg_prompt(args, cls: dict) -> str:
    p = _resolve_analyze_tg_params(args, cls)
    guide = load_worker_guide("analyze-tg")
    rate_line = (f"cooling_rate_K_per_ns: {p['selected_rate_K_per_ns']}  # tg_rate_index={p['tg_rate_index']}; "
                 f"record this (rate, Tg_K) pair — input to this run's multirate fit\n"
                 if p['selected_rate_K_per_ns'] is not None else "")
    return f"""\
tg_log_path:       {p['tg_log_path']}    # pass as log_file=
tg_data_file:      {p['tg_data_file']}    # pass as tg_data_file= — required for ΔCp mass normalisation
per_t_dump_file:   {p['per_t_dump_file']}    # pass as per_t_dump_file= — with tg_data_file it enables the structural block
backbone_types:    {p['backbone_types'] or 'null'}    # pass as backbone_types= — without it P2 is null at every T
enthalpy_col:      {p['enthalpy_col']}    # pass as enthalpy_col=
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
{rate_line}output_dir:        {p['output_dir']}
graphs_dir:        {p['graphs_dir']}
method_gap_exempt: {str(p['method_gap_exempt']).lower()}    # pass as method_gap_exempt= — pass the false too, never omit
tasks:
  - extract_thermal

Every field above annotated with `# pass as` is an argument of extract_thermal. Pass each one on
the call, including the ones whose value is null or false. Omitting an argument is a schema error,
not a default.

--- Worker Guide (THERMAL_ANALYSIS) ---
{guide}
"""


def _resolve_analyze_tg_multirate_params(args, cls: dict) -> dict:
    """Resolved values for the multirate Tg aggregation stage — consumed by
    analyze_tg_multirate_prompt's text template and, identically, by
    run_deterministic_replicate.py's scripted extract_tg_multirate.py call."""
    output_dir = args.output_dir or f"{REPO_ROOT}/data/{args.run_name}/raw/"
    script = str(REPO_ROOT / "mcp-servers/mcp-lammps-engine"
                 / "analysis_scripts/extract_tg_multirate.py")
    return {
        "output_dir": output_dir,
        "script": script,
        "dsc_equiv_rate_K_per_ns": cls.get("dsc_equiv_rate_K_per_ns", 1.6667e-10),
        "mr_rates": (args.mr_rates or "").replace(",", " ").strip(),
        "mr_tg_values": (args.mr_tg_values or "").replace(",", " ").strip(),
        "polymer_name": args.run_name,
        # regime exempts the slope-sign gate for rubbery polymers (T_workflow >> Tg): a
        # negative rate-dependence slope is scatter, not contamination, so no false-positive
        # reroll.
        "regime": _regime(args, cls),
    }


def analyze_tg_multirate_prompt(args, cls: dict) -> str:
    """Aggregate per-rate (rate, Tg_MD) pairs: log-linear + VF fit, extrapolated to the
    DSC-equivalent rate. The orchestrator supplies --mr_rates / --mr_tg_values from this
    run's per-rate analyze-tg results (fit_quality >= ACCEPTABLE); the worker runs the
    emitted command verbatim."""
    p = _resolve_analyze_tg_multirate_params(args, cls)
    guide = load_worker_guide("analyze-tg-multirate")
    rates_ph = p["mr_rates"] or "<FILL: space-separated rates from this run's sweeps, e.g. 40 80 100>"
    tg_vals_ph = p["mr_tg_values"] or "<FILL: matching Tg_MD values, same order>"
    command = (
        f"python3 {p['script']} \\\n"
        f"  --rates {rates_ph} \\\n"
        f"  --tg_values {tg_vals_ph} \\\n"
        f"  --slow_rate_ref {p['dsc_equiv_rate_K_per_ns']} \\\n"
        f"  --regime {p['regime']} \\\n"
        f"  --polymer_name {p['polymer_name']} \\\n"
        f"  --output_dir {p['output_dir']}"
    )
    return f"""\
task:              extract_tg_multirate
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
output_dir:        {p['output_dir']}
dsc_equiv_rate_K_per_ns: {p['dsc_equiv_rate_K_per_ns']}
mr_rates:          {p['mr_rates'] or "<FILL: this run's per-rate results>"}
mr_tg_values:      {p['mr_tg_values'] or "<FILL: this run's per-rate results>"}
command: |
  {command}

--- Worker Guide (THERMAL_ANALYSIS) ---
{guide}
"""


def _resolve_equil_check_params(args, cls: dict) -> dict:
    """Resolved values for the equil-check gate stage — consumed by equil_check_prompt's text
    template and, identically, by run_deterministic_replicate.py's scripted
    check_equilibration_comprehensive / extract_equilibrated_density / enforce_equilibration_gate
    calls."""
    output_dir = args.output_dir or f"{REPO_ROOT}/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    # Aromatic main-chain classes (ct_gate_reliable=false) cannot have their backbone path defined
    # by atom-type selection, so C(t)/C∞ are unreliable — do NOT arm the hard gate (null = advisory).
    ct_decay = cls.get("ct_min_decay_melt", 0.10) if cls.get("ct_gate_reliable", True) else None

    lammps_base = f"{REPO_ROOT}/data/{args.run_name}/lammps"
    # Phase-aware NPT production files: rubbery (T_workflow ≤ 300) ends at npt_production (7-run
    # chain — no npt_prod300 exists); glassy (T_workflow > 300) appends npt_prod300. The melt-NVT
    # log (nvt_production.log) is present in both. CLI --npt_prod_log/--npt_prod_dump/--data_path
    # still override when given.
    T_workflow = _resolve_t_workflow(args, cls)
    # Production NPT (thermo/density): rubbery (T ≤ 300) ends at npt_production; glassy (T > 300)
    # at npt_prod300 (cooled to 300 K). The structural/chain-relaxation checks (C(t), MSD, Rg, R_ee)
    # must run on the MELT trajectory — nvt_production at T_workflow, where chains are mobile — NOT
    # the production NPT, which for a glassy polymer is below Tg and yields trapped dynamics by
    # construction. check_equilibration_comprehensive decouples thermo (log_file) from structural
    # (dump_file), so a single call covers both: log_file = production NPT log, dump_file = melt dump.
    # phase=melt (glassy only — see equil stage's same guard): gate on the pre-cool melt
    # checkpoint (npt_production at T_workflow) instead of the post-cool npt_prod300, so a bad
    # melt is caught before the ~1-3 ns cool-to-300/produce-at-300 tail ever runs. Rubbery chains
    # already end at npt_production with nothing earlier to gate — phase forced to full there.
    phase = getattr(args, 'phase', 'full') or 'full'
    if T_workflow <= 300:
        phase = 'full'
    if phase == 'melt' or T_workflow <= 300:
        prod, npt_prod_temp = "npt_production", T_workflow
    else:
        prod, npt_prod_temp = "npt_prod300", 300.0
    # For the mechanized gate's density_value_binding check (glassy only): glass_data is npt_data
    # below; melt_data is the pre-cool NPT stage (npt_production_out.data), present in both the
    # 7-run rubbery chain (= npt_data itself there) and the 9-run glassy chain (a distinct earlier
    # stage than npt_prod300). density_value_binding compares melt vs. post-cool glass density —
    # it cannot run yet at phase=melt (no glass state exists), so equil_check_prompt omits
    # glass_data/melt_data/exp_density_gcm3/tg_K from the gate call and skips
    # extract_equilibrated_density entirely in that case (see phase branch below).
    return {
        "output_dir": output_dir,
        "phase": phase,
        "graphs_dir": graphs_dir,
        "exp_density_range": _exp_density_range(cls),
        "ct_min_decay_melt": ct_decay,
        # Enables the minimum-image half of the finite-size gate (L >= 2*cutoff_A).
        "cutoff_A": cls.get("cutoff_A"),
        "npt_prod_log_path": args.npt_prod_log or f"{lammps_base}/equil/{prod}/{prod}.log",
        "npt_prod_data_path": args.data_path or f"{lammps_base}/equil/{prod}/{prod}_out.data",
        "melt_dump_path": args.npt_prod_dump or f"{lammps_base}/equil/nvt_production/nvt_production.dump",
        "melt_data_path": f"{lammps_base}/equil/npt_production/npt_production_out.data",
        "npt_prod_temp_K": npt_prod_temp,
        "T_workflow_K": T_workflow,
        "exp_tg_point_K": _exp_tg_point(cls, args.run_name),
        "exp_density_point_gcm3": _exp_density_point(cls, args.run_name),
        # is_glassy and dp enable the require_glassy carve-out in the checker: when is_glassy=True
        # AND dp>=30, chain C(t)/end-to-end diffusion gates are advisory only (gate on density
        # SEM/CV/P2 exclusively). Derived from T_workflow so no explicit CLI flag needed.
        "is_glassy": T_workflow > 300,
        # regime oracle drives the require_rubbery carve-out (decision_policy.json): a rubbery
        # polymer (produced above Tg) has is_glassy=False, so require_glassy does NOT apply — but
        # its terminal chain-reptation metrics are unreachable at finite DP, so C(t)/MSD/Rg/τ_relax
        # must be advisory and the gate keys on density block-SEM + homogeneity + energy only.
        "regime": _regime(args, cls),
        "dp": getattr(args, 'dp', None) or cls.get('dp_typical'),
        "ct_gate_reliable": cls.get('ct_gate_reliable', True),
        # NB: cls.get(key, 'null') — the string 'null' is the default only when the key is
        # ABSENT; preserved verbatim (not is-not-None-coalesced) to match the pre-refactor prompt
        # text byte-for-byte.
        "alpha_glass_per_K": cls.get('alpha_glass_per_K', 'null'),
        "alpha_melt_per_K": cls.get('alpha_melt_per_K', 'null'),
        "backbone_types": args.backbone_types or cls.get("backbone_types"),
        # check_equilibration_comprehensive's ps axis: dt_ps = timestep_fs * dump_every / 1000.
        # dump_every self-heals (auto-detected from the dump header); timestep_fs does not, so a
        # dt_fs=2.0 class left on the 1.0 default reports tau_relax_ps and MSD 2x low -- and
        # tau_relax_ps sizes the EXTEND and feeds the cached t_equil_ns.
        "dt_fs": _pick(args.dt_fs, cls, 'dt_fs', 1.0),
    }


def equil_check_prompt(args, cls: dict) -> str:
    """Prompt for equilibration-checker (equil-check gate — equil check + density)."""
    p = _resolve_equil_check_params(args, cls)
    guide = load_worker_guide("equil-check")
    is_melt_phase = p["phase"] == "melt"
    if is_melt_phase:
        tasks_block = ("tasks:\n  - check_equilibration_comprehensive\n  - extract_equilibrated_density")
        density_note = (
            "### phase=melt: run extract_equilibrated_density against the MELT production log\n"
            "### (target_temp = T_workflow_K, not 300 K). Do NOT compare it to the 300 K\n"
            "### experimental band — that is the phase=full gate. The mechanized gate below\n"
            "### grades this melt density against experimental rho(T) evaluated at T_equil\n"
            "### (Mark 2007 equations in db/polymer_db.sqlite); it reports\n"
            "### melt_density_verdict = MELT_RHO_PASS | MELT_RHO_DEFICIT | MELT_RHO_NO_REFERENCE.\n"
            "### MELT_RHO_NO_REFERENCE means no usable equation exists for this polymer at this\n"
            "### temperature — the gate is UNARMED there, which is not a pass."
        )
        gate_block = f"""### MECHANIZED GATE (Step 2, replaces your own PASS/EXTEND/FAIL judgment — see EQUIL_CHECK guide):
### after Step 1 writes its JSON to output_dir, call the MCP tool
### mcp__mcp-lammps-engine__enforce_equilibration_gate with:
###   comprehensive_json = {p['output_dir']}equilibration_comprehensive.json
###   regime              = {p['regime']}
###   dp                  = {p['dp'] if p['dp'] is not None else 'null'}
###   ct_gate_reliable    = {str(p['ct_gate_reliable']).lower()}
###   out_dir             = {p['output_dir']}
###   exp_density_gcm3    = null
###   tg_K                = null
###   t_equil_K           = {p['T_workflow_K']}
###   glass_data          = null
###   melt_data           = null
###   alpha_glass_per_K   = null
###   alpha_melt_per_K    = null
###   phase               = melt
###   polymer_class       = {args.polymer_class.upper()}
###   polymer_name        = {_v(getattr(args, 'polymer_name', None) or _melt_reference_db_name(cls, args.run_name), 'null')}
### Pass every argument above, including the nulls — omitting one is a schema error, not a
### default. The nulls are deliberate here: density_value_binding's
### melt-vs-glass cooling-contraction diagnosis (UNDER_ANNEALED_COOLING / MELT_STAGE_DEFICIT)
### cannot run without a post-cool glass state, which doesn't exist yet at this checkpoint. This
### gate evaluates the structural/thermo gates that ARE meaningful on the melt trajectory alone
### (density/energy drift, block-SEM, Rg CV, P2, density-homogeneity CV, chain dimensions, C(t))
### plus melt_density_in_band, which compares the melt density directly against experimental
### rho(T) at T_equil and so needs no glass state — a
### STRUCTURAL_FAIL here with a density_homogeneity-only remedy note is the melt-mixing signal
### /recover's MELT-MIXING procedure handles; it is NOT re_melt_slow_recool/heavy_melt_anneal_probe
### (those require the melt-vs-glass split this call can't perform).
### Use its "verdict" field (PASS | EXTEND | STRUCTURAL_FAIL | FAIL) as equil_verdict directly."""
    else:
        tasks_block = "tasks:\n  - check_equilibration_comprehensive\n  - extract_equilibrated_density"
        density_note = (
            "### D-05 REQUIREMENT (PEEK2 I-04): return result[\"d05_markdown_path\"] (the tool writes\n"
            f"### the block to {p['output_dir'].rstrip('/')}/d05_block.md) as d05_markdown_path in your RESULT block.\n"
            "### Do NOT paste the block itself — the orchestrator splices it into run_log.md with\n"
            "### orchestration/scripts/write_d05.py. It contains the real Rg/MSD/density/C(t)/R_ee\n"
            "### values, so no [X ± Y] / [X]% / [PASS / FAIL] placeholder may survive in run_log.md."
        )
        gate_block = f"""### MECHANIZED GATE (Step 3, replaces your own PASS/EXTEND/FAIL judgment — see EQUIL_CHECK guide):
### after Steps 1-2 write their JSON to output_dir, call the MCP tool
### mcp__mcp-lammps-engine__enforce_equilibration_gate with:
###   comprehensive_json = {p['output_dir']}equilibration_comprehensive.json
###   regime              = {p['regime']}
###   dp                  = {p['dp'] if p['dp'] is not None else 'null'}
###   ct_gate_reliable    = {str(p['ct_gate_reliable']).lower()}
###   exp_density_gcm3    = {p['exp_density_point_gcm3'] if p['exp_density_point_gcm3'] is not None else 'null'}
###   tg_K                = {p['exp_tg_point_K'] if p['exp_tg_point_K'] is not None else 'null'}
###   t_equil_K           = {p['T_workflow_K']}
###   glass_data          = {p['npt_prod_data_path']}
###   melt_data           = {p['melt_data_path']}
###   out_dir             = {p['output_dir']}
###   alpha_glass_per_K   = {p['alpha_glass_per_K']}
###   alpha_melt_per_K    = {p['alpha_melt_per_K']}
###   phase               = full
###   polymer_class       = {args.polymer_class.upper()}
###   polymer_name        = {_v(getattr(args, 'polymer_name', None) or _melt_reference_db_name(cls, args.run_name), 'null')}
### Pass every argument above, including the ones whose value is null — omitting one is a schema
### error, not a default.
### alpha_glass_per_K/alpha_melt_per_K are curated per-class values (polymer_rules.json) or,
### for off-table/low-medium-confidence classes, planner-sourced from literature_grounding.json's
### CTE evidence — collected once at plan time, never searched live inside this gate. null means
### no class- or grounding-specific value exists; the tool falls back to its own generic default
### (2.5e-4 / 6.0e-4 per K) and the density_value_binding diagnosis is generic-CTE quality.
### One call — it runs assess_cooling_contraction internally when needed and returns the final
### verdict directly (no needs_probe round-trip). Use its "verdict" field (PASS | EXTEND |
### STRUCTURAL_FAIL | FAIL) as equil_verdict directly. Do NOT override it with your own reading
### of the numbers. (orchestration/enforce_gate.py --live is the same logic as a Bash-callable
### CLI, kept for retrospective/offline auditing — not used by this live prompt.)"""
    return f"""\
phase:             {p['phase']}
npt_prod_log_path: {p['npt_prod_log_path']}
melt_dump_path:    {p['melt_dump_path']}
npt_prod_temp_K:   {p['npt_prod_temp_K']}   # target_temp= for extract_equilibrated_density
equil_data_path:   {p['npt_prod_data_path']}
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
backbone_types:    {p['backbone_types'] or '<FILL from inspect_data_file>'}
ct_min_decay_melt: {p['ct_min_decay_melt'] if p['ct_min_decay_melt'] is not None else 'null'}   # pass as ct_min_decay= ; null ⇒ aromatic main chain, C(t)/C∞ advisory only — pass the null, never omit
cutoff_A:          {p['cutoff_A'] if p['cutoff_A'] is not None else 'null'}   # pass as cutoff_A= — arms the minimum-image check L >= 2*cutoff_A
dt_fs:             {p['dt_fs']}   # pass as timestep_fs= — sets the ps axis (dt_ps = timestep_fs*dump_every/1000); NOT auto-detected, unlike dump_every
is_glassy:         {str(p['is_glassy']).lower()}   # True → require_glassy carve-out: C(t)/Rg/MSD gates are advisory; gate only on density SEM/CV/P2
regime:            {p['regime']}   # if rubbery: require_rubbery carve-out applies — C(t)/MSD/Rg/τ_relax ADVISORY; verdict gates ONLY on density block-SEM<1% AND Poisson-corrected homogeneity signal CV<=0.11 AND n_eff_density>=20 AND energy drift/SEM AND finite size; do NOT EXTEND/FAIL on reptation metrics alone. If glassy: no carve-out from this line (see is_glassy for require_glassy).
dp:                {p['dp'] if p['dp'] is not None else 'null'}   # DP≥30 required for require_glassy carve-out to apply. NOTE: a class with ct_gate_reliable=false (aromatic main chain) already has ct_min_decay=null above, so its melt-diffusion C(t) gate is suppressed INDEPENDENT of DP — a DP<30 aromatic cell still passes equil on the structural gates (density/SEM/CV/P2/Rg). The DP≥30 clause only bites classes that would otherwise arm ct_min_decay.
exp_density_range: {p['exp_density_range']}
output_dir:        {p['output_dir']}
graphs_dir:        {p['graphs_dir']}
{tasks_block}

Every field above is an argument of the tool named in its comment. Pass each one on the call,
including the ones whose value is null. Omitting an argument is a schema error, not a default.

{density_note}

{gate_block}

--- Worker Guide (EQUIL_CHECK) ---
{guide}
"""


def _resolve_murnaghan_params(args, cls: dict) -> dict:
    """Resolved values for the Murnaghan BM stage — consumed by murnaghan_prompt's text
    template and, identically, by run_deterministic_replicate.py's scripted
    run_bulk_modulus_series call."""
    lammps_base = f"{REPO_ROOT}/data/{args.run_name}/lammps"
    return {
        "lammps_flags": _lammps_flags(args.lammps_flags, cls),
        "work_dir": args.work_dir or f"{REPO_ROOT}/data/{args.run_name}/lammps/mechanical",
        "is_glassy": _is_glassy(args, cls),
        "bm_pressures_atm": cls.get("bm_pressures_atm", None),
        "dt_fs": _pick(args.dt_fs, cls, "dt_fs", 1.0),
        "equil_data_path": args.data_path or f"{lammps_base}/equil/npt_production/npt_production_out.data",
        "temp_K": 300.0,
        # recover.md tunes this both ways -- npt_steps x2 to re-run a non-monotonic pressure
        # point, 200000 to fit a GPU that OOM'd on the default. A literal here made both
        # remedies unreachable: the prompt emitted 500000 whatever the recovery asked for.
        "npt_steps": _pick(getattr(args, "bm_npt_steps", None), cls, "bm_npt_steps", 500000),
        "gpu_ids": args.gpu_ids,
        "mpi_ranks": args.mpi_ranks,
        "engine": args.engine,
        "velocity_seed": _velocity_seed(args),
    }


def murnaghan_prompt(args, cls: dict) -> str:
    """Prompt for murnaghan-worker (rubbery BM pressure series submission)."""
    p = _resolve_murnaghan_params(args, cls)
    guide = load_worker_guide("murnaghan")
    # Glassy polymers ALWAYS submit. The guide's Rule B rubbery null-return guard has been
    # mis-applied to glassy cells when Tg metadata was degraded (POOR fits / single-rate
    # fallback) → worker returned null instead of submitting (PEEK2 I-02). Assert imperatively,
    # above the guide, so this overrides Rule B at prompt-assembly time.
    glassy_assertion = (
        "### ASSERTION (overrides guide Rule B): is_glassy=true → SUBMIT the Murnaghan series "
        "NOW, regardless of bm_pressures_atm being null. The rubbery null-return guard does NOT "
        "apply to glassy cells. Do not return an all-null RESULT.\n\n"
    ) if p["is_glassy"] else ""
    # 2026-08-09: rubbery+null used to be a deliberate skip (all-null RESULT, fluctuation-only
    # fallback). That's retired -- every rubbery class now gets a real Murnaghan attempt via the
    # PROBE ladder (guides/MURNAGHAN.md). Same belt-and-suspenders reasoning as glassy_assertion
    # above: assert imperatively in the prompt itself, don't rely solely on the worker reading it
    # off the markdown guide.
    rubbery_probe_assertion = (
        "### ASSERTION (overrides old guide Rule B): bm_pressures_atm is null and is_glassy=false "
        "→ SUBMIT NOW using the PROBE ladder [-200, 0, 3000, 7000, 15000] from "
        "guides/MURNAGHAN.md. Do NOT return an all-null RESULT -- that behavior was retired "
        "2026-08-09; every rubbery class gets a real Murnaghan attempt now.\n\n"
    ) if (not p["is_glassy"] and not p["bm_pressures_atm"]) else ""
    return f"""\
{glassy_assertion}{rubbery_probe_assertion}equil_data_path:   {p['equil_data_path']}
lammps_flags:      {p['lammps_flags']}   # pass as use_pcff=/use_trappe=/use_opls= — all default False, i.e. the wrong pair_style
polymer_class:     {args.polymer_class.upper()}
run_name:          {args.run_name}
work_dir:          {p['work_dir']}/bm_series
is_glassy:         {str(p['is_glassy']).lower()}
bm_pressures_atm:  {p['bm_pressures_atm']}   # pass as pressures_atm=
temp_K:            {p['temp_K']}   # pass as temp_K=
npt_steps:         {p['npt_steps']}   # pass as npt_steps=
dt_fs:             {p['dt_fs']}   # pass as dt_fs=
gpu_ids:           "{p['gpu_ids']}"   # pass as gpu_ids=
mpi_ranks:         {p['mpi_ranks']}   # pass as mpi=
engine:            "{p['engine']}"   # pass as engine= — the "gpu" default silently ignores a KOKKOS build
velocity_seed:     {p['velocity_seed']}   # pass as velocity_seed= — required, never null

Every field above is an argument of run_bulk_modulus_series. Pass each one on the call, including
the ones whose value is null. Omitting an argument is a schema error, not a default.

--- Worker Guide (MURNAGHAN) ---
{guide}
"""


def _resolve_analyze_bm_params(args, cls: dict) -> dict:
    """Resolved values for the BM extraction stage — consumed by analyze_bm_prompt's text
    template and, identically, by run_deterministic_replicate.py's scripted
    extract_bulk_modulus{,_murnaghan,_deform} call."""
    output_dir = args.output_dir or f"{REPO_ROOT}/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    lammps_base = f"{REPO_ROOT}/data/{args.run_name}/lammps"
    _k_from_cls = _exp_K_range(cls)
    exp_K = [
        args.exp_K_min if args.exp_K_min is not None else _k_from_cls[0],
        args.exp_K_max if args.exp_K_max is not None else _k_from_cls[1],
    ]
    K_deform_rate_slow_inv_s = cls.get("K_deform_rate_slow_inv_s", None)
    return {
        "output_dir": output_dir,
        "graphs_dir": graphs_dir,
        "npt_prod_log_path": args.npt_prod_log or f"{lammps_base}/equil/npt_prod300/npt_prod300.log",
        "exp_K_range": exp_K,
        "bm_pressures_atm": cls.get("bm_pressures_atm", None),
        "strain_rate_per_fs": cls.get("K_deform_rate_inv_s", 1e8) * 1e-15,
        "strain_rate_slow_per_fs": (K_deform_rate_slow_inv_s * 1e-15
                                     if K_deform_rate_slow_inv_s is not None else None),
        "K_strain_max": cls.get("K_strain_max", 0.03),
        "deform_log_path": getattr(args, 'deform_log', None),
        "deform_log_path_slow": getattr(args, 'deform_log_slow', None),
        "murnaghan_log_files": getattr(args, 'murnaghan_logs', None),
        # extract_bulk_modulus_deform reconstructs strain as
        # eps(step) = strain_rate * (step - step_0) * timestep, so timestep must be the deck's
        # own dt. Left on the 1.0 default, a dt_fs=2.0 class reports half the strain and twice K.
        "dt_fs": _pick(args.dt_fs, cls, "dt_fs", 1.0),
    }


def analyze_bm_prompt(args, cls: dict) -> str:
    """Prompt for bulk-modulus-extractor (BM extraction, all four routing paths)."""
    p = _resolve_analyze_bm_params(args, cls)
    deform_log_line = (f"deform_log_path:     {p['deform_log_path']}"
                        if p['deform_log_path'] else "deform_log_path:     null")
    deform_log_slow_line = (f"deform_log_path_slow: {p['deform_log_path_slow']}"
                             if p['deform_log_path_slow'] else "deform_log_path_slow: null")
    murnaghan_line = (f"murnaghan_log_files: {p['murnaghan_log_files']}"
                       if p['murnaghan_log_files'] else "murnaghan_log_files: null")

    guide = load_worker_guide("analyze-bm")
    return f"""\
{deform_log_line}
{deform_log_slow_line}
{murnaghan_line}
npt_prod_log_path: {p['npt_prod_log_path']}   # pass as npt_prod_log= to extract_bulk_modulus_murnaghan
bm_pressures_atm:  {p['bm_pressures_atm']}   # pass as pressures_atm=
exp_K_range:       {p['exp_K_range']}
strain_rate_per_fs: {p['strain_rate_per_fs']:.2e}   # pass as strain_rate=
strain_rate_slow_per_fs: {f"{p['strain_rate_slow_per_fs']:.2e}" if p['strain_rate_slow_per_fs'] is not None else "null"}   # pass as strain_rate_2= (with log_file_2)
K_strain_max:      {p['K_strain_max']}   # pass as strain_max=
dt_fs:             {p['dt_fs']}   # pass as timestep= to extract_bulk_modulus_deform — the strain axis is strain_rate*steps*timestep
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
output_dir:        {p['output_dir']}
graphs_dir:        {p['graphs_dir']}

Every field above annotated with `# pass as` is an argument of the routed tool. Pass each one on
the call, including the ones whose value is null. Omitting an argument is a schema error, not a
default.

--- Worker Guide (BM_ANALYSIS) ---
{guide}
"""


def _resolve_run_summary_params(args, cls: dict) -> dict:
    """Resolved values for the run-summary stage — consumed by run_summary_prompt's text
    template and, identically, by run_deterministic_replicate.py's scripted
    generate_run_summary call.

    Every field is derived from CLI flags + the (plan-overlaid) class defaults + the
    deterministic output_dir convention — NOT from the plan's decisions[] list or the --plan
    path — so a deterministic plan still produces byte-identical output to the no-plan path
    (enforced by tests/test_plan_reproducibility.py). The plan provenance is carried by reading
    raw/run_plan.json (the convention path below).
    """
    output_dir = args.output_dir or f"{REPO_ROOT}/data/{args.run_name}/raw/"
    graphs_dir = output_dir.replace("/raw/", "/graphs/").replace("/raw", "/graphs")
    run_plan = f"{output_dir.rstrip('/')}/run_plan.json"

    # Priority: explicit CLI min/max (thread from exp-lookup-worker) > --exp_tg_K CLI > DB query
    #           > polymer_rules.json median. The explicit min/max path lets the orchestrator pass
    #           condition-matched experimental ranges from exp-lookup-worker instead of hand-entering
    #           a tight floor (which caused a 0.07% density false FAIL, PVC2).
    _db = _db_exp_lookup(args.polymer_class, getattr(args, 'polymer_name', None))
    _tg_min, _tg_max = getattr(args, 'exp_tg_min', None), getattr(args, 'exp_tg_max', None)
    _tg_override = getattr(args, 'exp_tg_K', None)
    if _tg_min is not None and _tg_max is not None:
        exp_tg = [_tg_min, _tg_max]
    elif _tg_override is not None:
        exp_tg = [round(_tg_override - 20), round(_tg_override + 20)]
    elif _db.get("tg_median_K") is not None:
        exp_tg = [round(_db["tg_median_K"] - 20), round(_db["tg_median_K"] + 20)]
    else:
        exp_tg = _exp_tg_range(cls, run_name=args.run_name)

    # Density: explicit CLI min/max > DB value ±5% > polymer_rules.json median ±5%
    _dens_min, _dens_max = getattr(args, 'exp_density_min', None), getattr(args, 'exp_density_max', None)
    if _dens_min is not None and _dens_max is not None:
        exp_density = [_dens_min, _dens_max]
    elif _db.get("density_gcm3") is not None:
        _d = _db["density_gcm3"]
        exp_density = [round(_d * 0.95, 3), round(_d * 1.05, 3)]
    else:
        exp_density = _exp_density_range(cls)

    # K: CLI override > DB range (if genuine range) > polymer_rules.json range
    # A DB range of [x, x] (single-point measurement) is treated as missing — it must not
    # override the polymer_rules class range, which covers all class members.
    _k_from_cls = _exp_K_range(cls)
    _k_from_db = _db.get("K_range_GPa")
    if _k_from_db and (_k_from_db[1] - _k_from_db[0]) < 0.01:
        _k_from_db = None  # degenerate single-point DB entry; fall through to polymer_rules
    exp_K = [
        args.exp_K_min if args.exp_K_min is not None else (
            _k_from_db[0] if _k_from_db else _k_from_cls[0]
        ),
        args.exp_K_max if args.exp_K_max is not None else (
            _k_from_db[1] if _k_from_db else _k_from_cls[1]
        ),
    ]

    dp = args.dp if args.dp is not None else cls.get("dp_typical")
    nchain = args.nchain if args.nchain is not None else cls.get("nchain")
    charge_method = args.charge_method or cls.get("charge_method")
    ff = args.ff or cls.get("preferred_ff", "pcff")
    d01 = args.d01 or ff
    d02 = args.d02 or charge_method
    d03 = args.d03 or cls.get("electrostatics")
    d04 = args.d04 or (f"DP={dp}, {nchain} chains" if dp and nchain else None)

    _slope_gate = getattr(args, 'slope_gate_pass', None)
    tg_path_label = (
        "single-rate fallback (slope_gate=False; class fallback rate — plan "
        "tg_slope_gate_fallback, default highest)"
        if _slope_gate is False
        else "slowest-rate folder (slope_gate=True or N/A)"
    )
    return {
        "output_dir": output_dir,
        "graphs_dir": graphs_dir,
        "run_plan": run_plan,
        "exp_tg_range": exp_tg,
        "exp_density_range": exp_density,
        "exp_K_range": exp_K,
        "dp": dp,
        "nchain": nchain,
        "charge_method": charge_method,
        "ff": ff,
        "d01_ff": d01,
        "d02_charges": d02,
        "d03_electrostatics": d03,
        "d04_system_size": d04,
        "slope_gate_pass": _slope_gate,
        "tg_path_label": tg_path_label,
        # Flory-Fox K for the DP correction of the EXPERIMENTAL Tg band. Absent for most
        # classes -- no citable primary measurement -- and absence means the band is graded
        # uncorrected, never that a generic K is substituted.
        "tg_fox_flory_K": _fox_flory_K(cls, args.run_name),
    }


def run_summary_prompt(args, cls: dict) -> str:
    """Prompt for run-summary-worker (always-terminal, calls generate_run_summary)."""
    p = _resolve_run_summary_params(args, cls)
    return f"""\
run_name:          {args.run_name}
polymer_class:     {args.polymer_class.upper()}
smiles:            {_v(args.smiles)}
ff:                {p['ff']}
charge_method:     {_v(p['charge_method'], 'null')}
dp:                {_v(p['dp'], 'null')}
n_chains:          {_v(p['nchain'], 'null')}
n_atoms:           {_v(getattr(args, 'n_atoms', None), 'null')}
date_start:        {_v(args.date_start, 'null')}
date_end:          {_v(args.date_end, 'null')}
d01_ff:            {_v(p['d01_ff'], 'null')}
d02_charges:       {_v(p['d02_charges'], 'null')}
d03_electrostatics: {_v(p['d03_electrostatics'], 'null')}
d04_system_size:   {_v(p['d04_system_size'], 'null')}
d05_verdict:       {args.d05 or '<FILL from equil-checker RESULT>'}
d06_tg_fit_quality: {_v(args.tg_fit_quality, 'N/A (not requested)')}
run_plan:          {p['run_plan']}   # always pass to generate_run_summary --run_plan (skip if file absent)
exp_tg_range:      {p['exp_tg_range']}
exp_density_range: {p['exp_density_range']}
exp_K_range:       {p['exp_K_range']}
tg_fox_flory_K:    {_v(p['tg_fox_flory_K'], 'null')}   # Flory-Fox K (K*g/mol); pass to generate_run_summary --tg_fox_flory_K. null ⇒ omit the flag, band graded uncorrected
n_replicates:      {_v(getattr(args, 'n_replicates', None), 'N/A')}   # replicate count for this run (single-run multirate protocol: 1); pass to generate_run_summary --n_replicates
tg_path:           {_v(getattr(args, 'tg_path', None), 'null')}   # explicit canonical tg_summary.json path ({p['tg_path_label']}); pass to generate_run_summary --tg_path
slope_gate_pass:   {_v(p['slope_gate_pass'], 'null')}   # False → single-rate fallback Tg; point --tg_path at that rate's tg_summary.json. generate_run_summary has no --tg_k flag — passing one fails schema validation
output_dir:        {p['output_dir']}
graphs_dir:        {p['graphs_dir']}

Forward every field above to generate_run_summary as its matching --flag (dp→--dp,
n_chains→--n_chains, n_atoms→--n_atoms, charge_method→--charge_method, date_start→--date_start,
date_end→--date_end, d01_ff→--d01, …, d05_verdict→--d05, d06_tg_fit_quality→--d06,
run_plan→--run_plan). Skip any field whose value is `null`.

# generate_run_summary returns {{"status":"submitted","run_id":...}} but it completes IN-PROCESS in
# seconds — do NOT poll with get_run_status (you have no such tool). After the call, Read
# {p['output_dir']}run_summary.json directly and parse it.
"""


_STAGE_RESOLVERS = {
    "build":                _resolve_build_params,
    "equil":                _resolve_equil_params,
    "tg":                   _resolve_tg_params,
    "deform":                _resolve_deform_params,
    "analyze-tg":           _resolve_analyze_tg_params,
    "analyze-tg-multirate": _resolve_analyze_tg_multirate_params,
    "equil-check":          _resolve_equil_check_params,
    "murnaghan":            _resolve_murnaghan_params,
    "analyze-bm":           _resolve_analyze_bm_params,
    "run-summary":          _resolve_run_summary_params,
    # "born" has no resolver — the stage is removed; born_prompt raises directly.
}


def resolve_stage_params(stage: str, args, cls: dict) -> dict:
    """Resolve a stage's routing/physics decisions into a plain dict of concrete values —
    the single source of truth consumed by both this file's text-prompt builders (unchanged
    behavior; tests/test_plan_reproducibility.py enforces byte-identity with the pre-refactor
    output) and orchestration/run_deterministic_replicate.py's scripted MCP-call path, so a
    routing bug fix here can never silently diverge between the two."""
    resolver = _STAGE_RESOLVERS.get(stage)
    if resolver is None:
        raise ValueError(f"resolve_stage_params: no resolver for stage {stage!r} "
                          f"(valid: {sorted(_STAGE_RESOLVERS)})")
    return resolver(args, cls)


# ─── CLI ──────────────────────────────────────────────────────────────────────

STAGE_MAP = {
    "build":        build_prompt,
    "equil":        equil_prompt,
    "tg":           tg_prompt,
    "deform":       deform_prompt,
    "born":         born_prompt,
    "murnaghan":    murnaghan_prompt,
    "analyze-tg":   analyze_tg_prompt,
    "analyze-tg-multirate": analyze_tg_multirate_prompt,
    "equil-check":  equil_check_prompt,
    "analyze-bm":   analyze_bm_prompt,
    "run-summary":  run_summary_prompt,
}


def main():
    p = argparse.ArgumentParser(
        description="Generate a fully-formed PolyJarvis worker prompt.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Workers: build | equil | tg | deform | murnaghan | analyze-tg | analyze-tg-multirate | equil-check | analyze-bm | run-summary",
    )
    p.add_argument("--stage", required=True, choices=list(STAGE_MAP),
                   metavar="STAGE",
                   help="build|equil|tg|deform|murnaghan|analyze-tg|analyze-tg-multirate|equil-check|analyze-bm|run-summary (born is removed — raises error)")
    p.add_argument("--run_name", required=True)
    p.add_argument("--polymer_class", required=True)
    p.add_argument("--plan",
                   help="Path to an approved run_plan.json. Overlays the plan's "
                        "decided_params onto the class defaults (scientific decisions); "
                        "runtime paths/gpu stay in the flags below. Deterministic plans "
                        "produce byte-identical output to the no-plan path.")
    p.add_argument("--smiles")
    p.add_argument("--data_path")
    p.add_argument("--phase", default="full", choices=["full", "melt", "cooldown"],
                   help="equil stage: full (default; rubbery — single submission) | melt "
                        "(glassy — submit only through npt_production, gate before cooling) | "
                        "cooldown (glassy — submit the saved post-gate stage tail from "
                        "--pending_cooldown_path). equil-check stage: full (default; final gate, "
                        "includes density_value_binding cooling-contraction diagnosis) | melt "
                        "(glassy pre-cool gate on npt_production/nvt_production — structural/"
                        "thermo gates only, no glass_data/melt_data/exp_density_gcm3 comparison).")
    p.add_argument("--pending_cooldown_path",
                   help="equil stage, phase=cooldown only: JSON file the phase=melt submission "
                        "wrote with the remaining (post-npt_production) stage list.")
    p.add_argument("--tg_start_data",
                   help="Tg sweep starting .data file (rubbery: npt_tg_prep_data = npt_melt at "
                        "T_equil_K). Overrides --data_path for the tg stage only. Glassy polymers "
                        "omit this flag and pass --data_path instead.")
    p.add_argument("--work_dir")
    p.add_argument("--gpu_ids", required=False, default=None,
                   help='Comma-separated GPU IDs, e.g. "0" or "0,1". '
                        'If omitted, derived from polymer_rules.json hardware_policy by FF '
                        '("" for CPU engine). Claim a free GPU with orchestration/pick_gpu.py.')
    p.add_argument("--mpi_ranks", type=int, required=False, default=None,
                   help="MPI processes per run. If omitted, derived from "
                        "hardware_policy by FF (never mpi=1 for PPPM classes).")
    p.add_argument("--engine", required=False, default=None,
                   choices=["gpu", "kokkos"],
                   help="Execution engine the worker forwards to run_lammps_chain / "
                        "run_lammps_script / generate_equilibration_workflow. If omitted, "
                        "derived from the plan's decided_params.engine or hardware_policy "
                        "(kokkos = full-offload; anything else → gpu).")
    p.add_argument("--emc_seed", type=int, required=False, default=None,
                   help="Fixed EMC cell-packing seed (build stage). If omitted, the builder "
                        "generates a random seed and reports it. For replication studies pass the "
                        "fixed seed from guides/REVISION_PARAMS.md so the cell is reproducible.")
    p.add_argument("--velocity_seed", type=int, required=False, default=None,
                   help="Fixed `velocity all create` RNG seed (equil/tg stages). If omitted, the "
                        "tool draws a random seed. Pin it (REVISION_PARAMS.md) for a reproducible "
                        "trajectory, not just a reproducible initial cell.")
    p.add_argument("--dp", type=int)
    p.add_argument("--nchain", type=int)
    # run-summary metadata (else sourced from the plan; see run_summary_prompt)
    p.add_argument("--n_atoms", type=int)
    p.add_argument("--charge_method")
    p.add_argument("--date_start")
    p.add_argument("--date_end")
    p.add_argument("--d01", help="run-summary: D-01 force-field choice")
    p.add_argument("--d02", help="run-summary: D-02 charges choice")
    p.add_argument("--d03", help="run-summary: D-03 electrostatics choice")
    p.add_argument("--d04", help="run-summary: D-04 system-size choice")
    p.add_argument("--lammps_flags")
    p.add_argument("--is_glassy", default=None,
                   help="true|false (deform, murnaghan). Pass the thermal track's determination. "
                        "If omitted, derived from the regime oracle (T_workflow > 300 K).")
    p.add_argument("--tg_k", type=float)
    p.add_argument("--tg_fit_quality")
    p.add_argument("--deform_log",
                   help="Path to npt_deform log, primary rate (analyze-bm, glassy deform fallback)")
    p.add_argument("--deform_log_slow",
                   help="Path to npt_deform log, slow rate (analyze-bm; enables rate-sensitivity "
                        "check in extract_bulk_modulus_deform). Omit if the slow-rate run wasn't submitted.")
    p.add_argument("--deform_rate_mode", default="primary", choices=["primary", "slow"],
                   help="deform stage: primary (calibrated rate, default) or slow (~10x lower rate, "
                        "orchestrator's second sequential spawn for the rate-sensitivity check).")
    p.add_argument("--murnaghan_logs",
                   help="JSON list of absolute log paths from murnaghan-worker (analyze-bm, rubbery+pressures)")
    p.add_argument("--d05",
                   help="equil_verdict from equil-checker RESULT: PASS|EXTEND|FAIL (run-summary stage)")
    p.add_argument("--npt_prod_log")
    p.add_argument("--npt_prod_dump")
    p.add_argument("--ff")
    p.add_argument("--backbone_types",
                   help="Atom type IDs as JSON list (equil-check and analyze-tg). Same list for "
                        "both — analyze-tg needs it for the per-T P2 nematic order.")
    p.add_argument("--enthalpy_col", default="Enthalpy",
                   help="LAMMPS thermo column name for enthalpy (analyze-tg; default 'Enthalpy')")
    p.add_argument("--out", action="store_true",
                   help="Write the prompt to data/<run_name>/raw/prompts/ and print only that "
                        "path, so the prompt body never enters the orchestrator's context. The "
                        "spawned worker reads the file itself.")
    p.add_argument("--output_dir")
    p.add_argument("--equil_data_path",
                   help="Path to equilibrated .data file (LAMMPS .data input to Tg sweep; required for ΔCp mass normalisation in extract_thermal)")
    # Physics knob overrides (all optional; default None → falls back to polymer_rules.json)
    p.add_argument("--npt_prod_ns", type=float,
                   help="NPT production time (ns); auto-sized by atom count if omitted")
    p.add_argument("--npt_cool_steps", type=int,
                   help="Override npt_cool stage step count (default: atom-count tier). "
                        "re_melt_slow_recool recovery lever — larger = slower cool ramp")
    p.add_argument("--npt_cool300_steps", type=int,
                   help="Override npt_cool300 stage step count (default: ~1ns, glassy only). "
                        "re_melt_slow_recool recovery lever — larger = slower cool to 300K")
    p.add_argument("--add_melt_npt", action="store_true", default=False,
                   help="Inject 05b melt isothermal NPT stage for rubbery classes (FF validation only)")
    p.add_argument("--T_equil_K", type=float,
                   help="Equilibration temperature (K) → temp= in generate_equilibration_workflow")
    p.add_argument("--T_anneal_high_K", type=float,
                   help="Peak annealing temperature (K) → max_temp= in generate_equilibration_workflow")
    p.add_argument("--tg_t_high_K", type=float,
                   help="Tg sweep start temperature (K)")
    p.add_argument("--tg_t_low_K", type=float,
                   help="Tg sweep end temperature (K)")
    p.add_argument("--tg_t_step_K", type=float,
                   help="Tg sweep step (K); halve for BORDERLINE R² recovery")
    p.add_argument("--tg_steps_per_t", type=int,
                   help="MD steps per temperature window; rejected with --tg_rate_index")
    p.add_argument("--bm_npt_steps", type=int,
                   help="MD steps per Murnaghan pressure point (default 500000)")
    p.add_argument("--tg_rate_index", type=int,
                   help="Index into tg_rates_K_per_ns list for multi-rate sweeps (0=slowest)")
    p.add_argument("--mr_rates",
                   help="analyze-tg-multirate: comma/space-separated cooling rates (K/ns) "
                        "from this run's per-rate Tg results, e.g. '40,80,100'")
    p.add_argument("--mr_tg_values",
                   help="analyze-tg-multirate: matching Tg_MD values (K), same order as --mr_rates")
    p.add_argument("--n_replicates", type=int, default=1,
                   help="run-summary: replicate count reported in results.tg.n_replicates "
                        "(single-run protocol: 1)")
    p.add_argument("--K_strain_max", type=float,
                   help="Max engineering strain for uniaxial deformation")
    p.add_argument("--K_deform_rate_inv_s", type=float,
                   help="Engineering strain rate (s⁻¹)")
    p.add_argument("--dt_fs", type=float,
                   help="MD timestep (fs); set 0.5 for 'lost atoms' recovery")
    p.add_argument("--density_initial", type=float,
                   help="Initial packing density (g/cm³); use for ESCALATE recovery (class default − 0.05) or Energy-NaN recovery (class default − 0.10)")
    p.add_argument("--properties", default="all",
                   help="Comma-separated properties to extract: density,tg,bulk_modulus or 'all'")
    p.add_argument("--exp_K_min", type=float,
                   help="Experimental bulk modulus lower bound (GPa); overrides polymer_rules.json")
    p.add_argument("--exp_K_max", type=float,
                   help="Experimental bulk modulus upper bound (GPa); overrides polymer_rules.json")
    p.add_argument("--exp_tg_K", type=float,
                   help="Experimental Tg override (K) for T_workflow_K decision; use for specific polymer "
                        "within a multi-polymer class (e.g. --exp_tg_K 213 for PCL within PEST)")
    p.add_argument("--exp_tg_min", type=float,
                   help="Experimental Tg lower bound (K) for run-summary grading; overrides DB/rules. "
                        "Thread from exp-lookup-worker. Pass with --exp_tg_max.")
    p.add_argument("--exp_tg_max", type=float,
                   help="Experimental Tg upper bound (K) for run-summary grading; overrides DB/rules.")
    p.add_argument("--exp_density_min", type=float,
                   help="Experimental density lower bound (g/cm³) for run-summary grading; overrides "
                        "DB/rules. Thread from exp-lookup-worker rather than hand-entering a tight floor "
                        "(a too-tight floor caused a 0.07%% false FAIL, PVC2 2026-06-23). With --exp_density_max.")
    p.add_argument("--exp_density_max", type=float,
                   help="Experimental density upper bound (g/cm³) for run-summary grading; overrides DB/rules.")
    p.add_argument("--polymer_name", default=None,
                   help="Canonical DB name for experimental lookup (e.g. 'Poly(methyl methacrylate)'). "
                        "Enables polymer-specific exp ranges from polymer_db.sqlite. "
                        "When omitted, falls back to the class-representative canonical pattern.")
    p.add_argument("--tg_path", default=None,
                   help="Explicit path to the canonical tg_summary.json for run-summary. "
                        "Normally the slowest-rate folder (e.g. tg_r40/tg_summary.json). "
                        "When slope_gate_pass=False, pass the highest-rate folder instead "
                        "(e.g. tg_r400/tg_summary.json — the single-rate fallback).")
    p.add_argument("--slope_gate_pass", type=lambda x: x.lower() == 'true', default=None,
                   help="Multirate log-linear slope gate result (true/false). False means "
                        "slope<=0 (contaminated sweep); tg_path should point to the highest-rate "
                        "fallback folder, not the slowest-rate folder. Threaded to run-summary-worker.")

    args = p.parse_args()

    rules = load_rules()
    cls = get_class_entry(rules, args.polymer_class, warn_on_miss=True)

    if args.plan:
        cls = apply_plan(cls, load_plan(args.plan), args)

    resolve_hardware(args, cls, rules)

    prompt_fn = STAGE_MAP[args.stage]
    prompt = prompt_fn(args, cls) + CWD_NOTE

    if not args.out:
        print(prompt)
        return

    # --out keeps the prompt body out of the orchestrator's context: it goes to a file the worker
    # reads itself, and stdout carries only the path. Stdout must stay exactly one line — every
    # diagnostic in this script already goes to stderr.
    if not args.run_name:
        p.error("--out requires --run_name")
    digest = hashlib.sha1(prompt.encode()).hexdigest()[:8]
    out_dir = REPO_ROOT / "data" / args.run_name / "raw" / "prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.stage}-{digest}.txt"
    out_path.write_text(prompt)
    print(out_path)


if __name__ == "__main__":
    main()
