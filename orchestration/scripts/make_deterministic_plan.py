#!/usr/bin/env python3
"""
make_deterministic_plan.py — Emit the deterministic planning artifacts for a polymer class.

Two subcommands. Both transcribe guides/polymer_rules.json, and build_decisions() is shared:

  run-plan   the full run_plan.json (class-default plan materializer)
  decision   the complete decision.json the novel-run-plan skill's literature critic then
             CRITIQUES (it does not author it -- see below)

`decision` lived in its own make_decision_scaffold.py until 2026-09-02; it was a 116-line leaf
whose only reason to import this module was build_decisions(), and finding "the thing that
writes decision.json" meant knowing that file existed.

`decision` stopped being a scaffold on 2026-09-02. It used to emit rationale=[] and blank
evidence for an agent to fill in; it now resolves every row itself -- solve_system_size (D-04),
select_hardware (D-08), the electrostatics_decision_guide and _metadata.primary_sources
citation records (D-01/D-02/D-03) -- and writes the rationale too. What is left for review is
`confidence`, which comes back "unreviewed" (invalid per scientific_control's VALID_CONFIDENCE)
and is now the ONLY thing blocking materialization. --baseline stamps "low" instead, for the
deterministic benchmark arm that runs with no LLM in the loop at all.

That inversion is the point: the autofilled file is a real end-to-end deterministic baseline,
and whatever the critic changes on top of it is the measurable LLM contribution. Evidence
written here is tagged origin="autofill" so benchmarks/.../metrics/llm_contribution.py can tell
the two apart.

Reproducibility guarantee: decided_params snapshots ONLY keys already present in
the class entry, with their existing values. stage_params.py overlays them as
{**cls, **decided_params}, which is therefore an identity for an unmodified plan.

`scientific_control.py` turns a decision into a reasoned plan and records the rationale,
evidence, uncertainty, confidence, and decision digest.

Usage:
  python3 orchestration/scripts/make_deterministic_plan.py run-plan \
      --run_name PE7 --polymer_class PHYC \
      [--smiles "*CC*"] [--properties density,tg,bulk_modulus] \
      [--out PATH]        # default: data/<run_name>/raw/run_plan.json; "-" = stdout

  python3 orchestration/scripts/make_deterministic_plan.py decision \
      --run_name PE7 --polymer_class PHYC --smiles "*CC*" \
      [--properties ...] [--out PATH] [--force] [--baseline]
                          # --smiles is REQUIRED here: all five decisions resolve per-molecule
                          # default: data/<run_name>/raw/decision.json; "-" = stdout
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules_common  # noqa: E402  -- module import so tests can monkeypatch rules_common.canonicalize
from rules_common import load_rules, get_class_entry, hardware_policy, resolve_ff_family  # shared rules access (single source of truth)
import track_registry  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage_params import _exp_tg_point, _regime_exp_tg  # reuse the proven resolvers, don't duplicate them
from select_system_size import derive_cell  # per-SMILES cell derivation; the class dp_typical/nchain keys were removed 2026-09-02
from select_system_size import solve_system_size, SYSTEM_MW_FLOOR_DOI  # noqa: E402  -- D-04, the same call materialize_plan makes
from select_hardware import select_hardware       # noqa: E402  -- D-08, live host + derived cell size
from hardware_runtime import gpu_status, host_matches  # noqa: E402  -- D-08 concurrent_load / host_match
from rules_common import primary_source, source_evidence  # noqa: E402  -- citations[] id -> real DOI

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DECISION_POLICY_PATH = REPO_ROOT / "orchestration" / "decision_policy.json"
# Decision-relevant class keys consumed by stage_params.py. Only keys that
# EXIST in the class entry are snapshotted, so the overlay stays an exact identity.
SNAPSHOT_KEYS = [
    "preferred_ff", "preferred_builder", "charge_method", "electrostatics",
    "cutoff_A", "dt_fs",
    "dp_typical", "nchain", "density_initial_gcm3",
    "T_equil_K", "annealing_T_high_K", "P_equil_atm", "final_T_K", "anneal_margin_K",
    "warmup_steps", "densify_ramp_steps", "densify_check_every_steps", "densify_steps_cap",
    "ff_activate_npt_steps", "anneal_heat_steps", "anneal_check_every_steps",
    "anneal_cap_steps", "cool_block_dT_K", "cool_block_hold_steps", "cool_block_hold_cap_steps",
    "stage7_min_steps", "stage7_cap_steps", "stage8_min_steps", "stage8_cap_steps",
    "tg_t_high_K", "tg_t_low_K", "tg_t_step_K", "tg_steps_per_t", "tg_rates_K_per_ns",
    "tg_min_steps_per_T", "tg_slope_gate_fallback",
    "K_deform_rate_inv_s", "K_deform_rate_slow_inv_s", "K_strain_max",
    "bm_pressures_atm", "ct_min_decay_melt",
    "alpha_glass_per_K", "alpha_melt_per_K",
]


def _policy_criteria() -> dict:
    """decision_id -> its policy's evaluate list, read straight from decision_policy.json --
    single source of truth so a row's criteria_evaluated can never drift from the policy that
    validate_run_plan.py checks it against."""
    policy = json.loads(DECISION_POLICY_PATH.read_text())
    return {p["decision_id"]: p.get("evaluate", []) for p in policy.get("policies", {}).values()}


def _build_hardware_decision(cls: dict, criteria_evaluated: list) -> dict:
    """D-08_hardware default: engine/mpi/gpu_per_run from hardware_policy.by_forcefield[fam],
    the same FF-family resolver stage_params.resolve_hardware uses. Deliberately NOT
    select_hardware.py's live-host/atom-count-aware defensibility check -- that needs a SMILES
    and nvidia-smi and stays the independent check validate_run_plan.py already runs; this is
    the pure, fast, deterministic class default."""
    hp = hardware_policy()
    fam = resolve_ff_family(cls.get("preferred_ff") or "", hp)
    default = hp.get("by_forcefield", {}).get(fam, {})
    choice = {"engine": default.get("engine"), "gpu_per_run": default.get("gpu_per_run"),
              "mpi_ranks": default.get("mpi")}
    evidence = ([{"claim": default["note"], "source": "polymer_rules.json:hardware_policy.by_forcefield"}]
                if default.get("note") else [])
    return {"id": "D-08_hardware", "choice": choice, "criteria_evaluated": criteria_evaluated,
            "evidence": evidence, "confidence": "class_default", "alternatives": []}


def _d04_choice(cls: dict, smiles: str | None) -> str:
    """D-04's default_choice string.

    guides/polymer_rules.json's per-class dp_typical/nchain were removed 2026-09-02 (every cell
    is now derived per-SMILES from the system-mass floor), so reading them off `cls` rendered the
    literal string "DP=None, nchain=None" for all 21 classes. Fall back to the same derive_cell()
    that select_system_size/materialize_plan use, so this string and decided_params cannot drift.
    """
    dp, nchain = cls.get("dp_typical"), cls.get("nchain")
    if (dp is None or nchain is None) and smiles:
        try:
            _dp, _n, _mw, _note = derive_cell(smiles, cls.get("preferred_ff", "") == "trappe-ua")
        except Exception:
            _dp = _n = None
        dp = dp if dp is not None else _dp
        nchain = nchain if nchain is not None else _n
    if dp is None or nchain is None:
        return "UNRESOLVED (no SMILES supplied; cell size is derived per-molecule)"
    return f"DP={dp}, nchain={nchain}"


def build_decisions(cls: dict, smiles: str | None = None) -> list:
    """Structured default decision rows carrying evidence/confidence/alternatives, mirroring
    run_summary.json decision IDs. Evidence is transcribed from existing class fields.

    Covers D-01_ff, D-02_charges, D-03_electrostatics, D-04_system_size, D-08_hardware --
    the decisions a planning agent can actually reason about before any simulation exists.
    D-05_convergence, D-06_tg_fit_quality, D-07_property_method are deliberately excluded:
    decision_policy.json defines all three as mechanized runtime gate verdicts (equil_verdict,
    tg_gate_verdict, bm_gate_verdict) to route on, not re-derive -- they have no pre-simulation
    default choice to annotate here and stay enforced solely via planned_stages success_criteria.

    "confidence" here is a fixed "class_default" placeholder. The scientific control layer
    replaces it with the planning agent's confidence before execution.
    """
    criteria = _policy_criteria()
    ff_evidence = []
    if cls.get("ff_justification_doi"):
        ff_evidence.append({"claim": cls.get("ff_note", "force field choice"),
                            "source_doi": cls.get("ff_justification_doi")})
    for cit in cls.get("citations", []):
        ff_evidence.append({"claim": "supporting validation", "citation": cit})

    conf = "class_default"
    return [
        {"id": "D-01_ff", "choice": cls.get("preferred_ff"),
         "criteria_evaluated": criteria.get("D-01_ff", []),
         "evidence": ff_evidence, "confidence": conf,
         "alternatives": cls.get("forcefield_alternatives", [])},
        {"id": "D-02_charges", "choice": cls.get("charge_method"),
         "criteria_evaluated": criteria.get("D-02_charges", []),
         "evidence": [], "confidence": conf, "alternatives": []},
        {"id": "D-03_electrostatics", "choice": cls.get("electrostatics"),
         "criteria_evaluated": criteria.get("D-03_electrostatics", []),
         "evidence": [{"claim": "see electrostatics_decision_guide",
                       "source": "polymer_rules.json:electrostatics_decision_guide"}],
         "confidence": conf, "alternatives": []},
        {"id": "D-04_system_size",
         "choice": _d04_choice(cls, smiles),
         "criteria_evaluated": criteria.get("D-04_system_size", []),
         "evidence": [], "confidence": conf, "alternatives": []},
        _build_hardware_decision(cls, criteria.get("D-08_hardware", [])),
    ]


# Re-exported: recovery_agent_cli, validate_run_plan and the tests all import this name.
STAGE_TRACK = track_registry.STAGE_TRACK


def build_planned_stages(cls: dict, properties: set, smiles: str | None = None) -> list:
    """Experiment DAG with per-stage success_criteria the Validator enforces."""
    # tg-stage accuracy bracket: central Tg estimate (see _exp_tg_point).
    exp_tg_bracket = _exp_tg_point(cls, smiles)
    # murnaghan deform-fallback hint: regime call, not the bracket -- _regime_exp_tg pads an
    # estimated Tg toward glassy (see its docstring), so this can disagree with the bracket.
    glassy_hint = ((regime_tg := _regime_exp_tg(cls, smiles)) is not None
                   and regime_tg > 300)

    def _s(stage, criteria, **extra):
        return {"stage": stage, "track": STAGE_TRACK[stage],
                "success_criteria": criteria, **extra}

    # WHICH stages, and in what order, comes from track_registry. WHAT each stage must satisfy
    # stays here: success_criteria need cls/smiles, and the registry deliberately owns no science.
    _CRITERIA = {
        "build":       {"data_file_written": True},
        "equil":       {"check_equilibration_comprehensive.overall_pass": True},
        "equil-check": {"equil_verdict": "PASS"},
        # Single-rate-primary: one sweep at the class's primary configured rate (see
        # stage_params.select_primary_tg_rate_index, shared with do_thermal and the cooldown).
        "tg":          {"bilinear_fit_r_squared_min": 0.80,
                        "t_range_brackets_exp_tg": exp_tg_bracket},
        "analyze-tg":  {},
        # Murnaghan always submits (2026-08-09): guides/MURNAGHAN.md's rubbery null-fallback
        # resolves to the PROBE ladder instead of an all-null RESULT, so there is no longer a
        # "rubbery without pressures -> fluctuation only, no submit stage" case.
        "murnaghan":   {"chain_submitted": True},
        # Primary only when shear/Young's/Poisson were requested -- they exist only on the
        # deformation path, so the registry forces mechanical_method and swaps this in for
        # murnaghan. Otherwise it is murnaghan's contingent fallback and never a plan entry.
        "deform":      {"chain_submitted": True},
        "analyze-bm":  {},
        "run-summary": {},
    }
    # Glassy carries the deform fallback; rubbery (empirical or PROBE ladder) does not. The
    # registry knows deform IS murnaghan's fallback slot; whether it attaches is a regime call,
    # which needs cls/smiles and therefore stays here.
    _EXTRA = {"murnaghan": {"fallback": "deform"}} if glassy_hint else {}

    return [_s(name, _CRITERIA[name], **_EXTRA.get(name, {}))
            for name in track_registry.planned_stage_names(properties)]


def _assert_tg_rates_feasible(cls: dict, polymer_class: str) -> None:
    """Reject a configured Tg rate set where any rate gives too few steps per temperature.

    Per-T simulation TIME (not step count) sets bilinear-fit quality: too few ps at each
    temperature collapses the Tg fit (cis-PBD2 r400=50ps, PEEK2 r160/r400 degenerate).
    Rate IS the per-T step knob (N = tg_t_step_K/(rate*dt*1e-6)), so an infeasible rate
    cannot be salvaged at run time — fail at plan time. Floor = tg_min_steps_per_T
    (default 200000 steps = 200 ps at dt=1fs; TraPPE dt=2fs classes set 100000 = 200 ps).
    """
    rates = cls.get("tg_rates_K_per_ns")
    t_step = cls.get("tg_t_step_K")
    if not rates or t_step is None:
        return
    dt = cls.get("dt_fs", 1.0)
    floor = cls.get("tg_min_steps_per_T", 200000)
    bad = [(r, int(t_step / (r * dt * 1e-6)))
           for r in rates if t_step / (r * dt * 1e-6) < floor - 1]
    if bad:
        max_rate = t_step / (floor * dt * 1e-6)
        raise ValueError(
            f"{polymer_class}: infeasible tg_rates_K_per_ns {rates} — "
            f"rate(s) {[b[0] for b in bad]} give {[b[1] for b in bad]} steps/T, below "
            f"tg_min_steps_per_T={floor} (tg_t_step_K={t_step}, dt_fs={dt}). Lower the rates "
            f"so N = tg_t_step_K/(rate*dt*1e-6) >= floor (max feasible rate = {max_rate:.0f} K/ns)."
        )


def make_plan(run_name: str, polymer_class: str, smiles, properties: set) -> dict:
    rules = load_rules()
    if polymer_class.upper() not in rules.get("classes", {}):
        raise ValueError(f"unknown polymer class {polymer_class!r}")
    cls = get_class_entry(rules, polymer_class)
    _assert_tg_rates_feasible(cls, polymer_class.upper())
    decided_params = {k: cls[k] for k in SNAPSHOT_KEYS if k in cls}
    # Regime call (see _regime_exp_tg): a novel polymer's Tg estimate now drives this instead of
    # defaulting glassy by omission, padded toward glassy for an uncertain estimate.
    exp_tg = _regime_exp_tg(cls, smiles)
    T_equil = decided_params.get("T_equil_K", 600.0)
    decided_params["T_workflow_K"] = 300.0 if (exp_tg is not None and exp_tg < 300) else T_equil
    uncertainties = [{
        "name": "scientific_review_pending",
        "dominant": True,
        "reduction_probe": "planning_agent_review",
    }]
    return {
        "schema_version": "1.0",
        "goal": f"Predict {', '.join(sorted(properties))} for {polymer_class.upper()}"
                + (f" ({smiles})" if smiles else ""),
        "run_name": run_name,
        "polymer_class": polymer_class.upper(),
        "smiles": smiles,
        "properties": sorted(properties),
        "confidence": "unreviewed",
        "plan_mode": "scaffold",
        "assumptions": [
            "polymer_rules.json class defaults are a starting hypothesis pending "
            "scientific-agent review.",
        ],
        "uncertainties": uncertainties,
        "decided_params": decided_params,
        "decisions": build_decisions(cls, smiles),
        "planned_stages": build_planned_stages(cls, properties, smiles),
        "critique": {"status": "pending_scientific_review", "rounds": 0, "findings": []},
        "provenance": {"generator": "make_deterministic_plan.py",
                       "generated_at": datetime.now(timezone.utc).isoformat()},
    }


CACHE_PATH_DEFAULT = REPO_ROOT / "guides" / "system_characterization_cache.json"


def make_plan_from_cache(run_name: str, polymer_class: str, smiles: str, canonical_smiles: str,
                          properties: set, cache_entry: dict) -> dict:
    """Materialize run_plan.json from a validated cache entry's frozen protocol -- the exact
    protocol previously proven to reach "accepted" for this exact molecule -- instead of
    polymer_rules.json class defaults. This is the "system, not class" fast path.

    D-08_hardware is the one exception: always resolved fresh via _build_hardware_decision,
    matching decision_policy.json's stance that hardware stays host-dependent and is never
    frozen/replayed (the cache's protocol.decisions never carries a D-08 row in the first place --
    write_characterization_cache.py drops it before freezing).
    """
    rules = load_rules()
    cls = get_class_entry(rules, polymer_class)
    protocol = cache_entry["protocol"]
    decided_params = dict(protocol["decided_params"])  # literal replay, no recomputation
    decisions = [dict(d) for d in protocol["decisions"]]
    decisions.append(_build_hardware_decision(cls, _policy_criteria().get("D-08_hardware", [])))
    return {
        "schema_version": "1.0",
        "goal": f"Predict {', '.join(sorted(properties))} for {polymer_class.upper()} ({smiles})",
        "run_name": run_name,
        "polymer_class": polymer_class.upper(),
        "smiles": smiles,
        "properties": sorted(properties),
        "confidence": "high",
        "plan_mode": "deterministic",
        "assumptions": [
            f"decided_params/decisions/planned_stages replayed verbatim from "
            f"guides/system_characterization_cache.json[{canonical_smiles!r}], validated by "
            f"run {cache_entry.get('source_run_name')!r} on {cache_entry.get('validated_at')}.",
        ],
        "uncertainties": [{"name": "none_dominant", "dominant": True, "reduction_probe": "none"}],
        "decided_params": decided_params,
        "decisions": decisions,
        "planned_stages": list(protocol["planned_stages"]),
        "critique": {"status": "protocol_validated_replay", "rounds": 0, "findings": []},
        "provenance": {"generator": "make_deterministic_plan.py:make_plan_from_cache",
                       "generated_at": datetime.now(timezone.utc).isoformat(),
                       "cache_canonical_smiles": canonical_smiles},
    }


def _try_cache(run_name: str, polymer_class: str, smiles, properties: set,
               cache_path: Path | None = None) -> dict | None:
    """Look up a validated protocol for this exact SMILES and, if it covers every requested
    property, materialize the plan from it. Returns None (never raises) on any miss -- no smiles,
    no cache file, no entry, not validated, insufficient coverage, or a polymer_class mismatch --
    so callers fall through to the class-default make_plan() unchanged."""
    if not smiles:
        return None
    path = cache_path or CACHE_PATH_DEFAULT
    if not path.exists():
        return None
    try:
        canonical = rules_common.canonicalize(smiles, isomeric=True)
    except (RuntimeError, subprocess.TimeoutExpired):
        return None
    try:
        cache = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None
    entry = cache.get(canonical)
    if not entry or not entry.get("protocol_validated"):
        return None
    if not set(entry.get("validated_properties", [])) >= properties:
        return None
    if str(entry.get("polymer_class", "")).upper() != polymer_class.upper():
        # Don't trust a cache entry recorded under a different class label -- fall back
        # rather than silently apply a different class's frozen protocol.
        return None
    return make_plan_from_cache(run_name, polymer_class, smiles, canonical, properties, entry)


# ---------------------------------------------------------------------------
# decision.json (the `decision` subcommand)
#
# This is the SMALL agent-facing file (PlanDecision's schema in scientific_control.py), not the
# full run_plan.json above. Since 2026-09-02 it is NOT a scaffold: it is a complete, deterministic
# decision. Every row is resolved here from this repo's own resolvers -- solve_system_size (D-04),
# select_hardware (D-08), polymer_rules.json's electrostatics_decision_guide (D-03) and its
# _metadata.primary_sources citation records (D-01/D-02/D-03) -- and every criterion the matching
# policy in decision_policy.json names gets its own evidence entry, including the criteria this
# layer honestly cannot reach (those say NOT MEASURED / NOT ASSESSABLE rather than going silent).
#
# The division of labour this establishes:
#
#   written here (origin="autofill")   default_choice, criteria_evaluated, evidence,
#                                      alternatives, rationale, assumptions,
#                                      dominant_uncertainty
#   left to the reviewer               confidence -- "unreviewed" is invalid per
#                                      scientific_control.py's VALID_CONFIDENCE, so it is now
#                                      the ONLY thing blocking materialization
#   the critic's only lever            overrides (always emitted {} here)
#
# `overrides` staying {} is load-bearing: materialize_plan() only auto-fills dp_typical/nchain
# for keys `overrides` does not already set, so writing the derived cell into overrides would
# suppress the very solve it came from and let the two paths drift.
#
# default_choice is READ-ONLY provenance: materialize_plan() reads only criteria_evaluated /
# evidence / alternatives off each row. To disagree with a shown default, add the corresponding
# key to top-level `overrides`.
#
# --baseline stamps confidence="low" instead, for the deterministic benchmark arm that runs with
# no LLM in the loop at all. Evidence written here is tagged origin="autofill" so
# benchmarks/.../metrics/llm_contribution.py scores it as baseline, never as LLM reasoning.
# ---------------------------------------------------------------------------

# cls["charge_method"] -> the facts D-02's three criteria need. Closed set: these four are the
# only values across all 21 classes in guides/polymer_rules.json.
_CHARGE_METHOD_FACTS = {
    "embedded": {
        "qm": False,
        "cost": "zero at plan time -- charges are the force field's own atom-type parameters; "
                "no separate QM or empirical charge step runs",
        "pairing": "FF-embedded charges are what the field was parameterized against; "
                   "substituting QM charges would break that internal consistency",
    },
    "bond-increment": {
        "qm": False,
        "cost": "zero at plan time -- EMC applies the field's INCREMENT table during the build",
        "pairing": "bond-increment is the Class II (PCFF/COMPASS) native scheme; the field's "
                   "valence and nonbond terms were fit alongside it",
    },
    "opls-library": {
        "qm": False,
        "cost": "zero at plan time -- charges come from the OPLS library by atom type",
        "pairing": "OPLS-AA ships library charges per type; they are part of the parameter set",
    },
    "none": {
        "qm": False,
        "cost": "zero -- united-atom sites carry no partial charge",
        "pairing": "TraPPE-UA apolar backbones are parameterized with no Coulomb term at all",
    },
    "gasteiger": {
        "qm": False,
        "cost": "negligible -- empirical electronegativity equalization, no QM",
        "pairing": "a fast empirical fallback; weaker than a field's native scheme",
    },
    "RESP": {
        "qm": True,
        "cost": "per-chemistry QM (HF/6-31G*) before any MD can start -- the dominant "
                "pre-simulation cost for a novel repeat unit",
        "pairing": "GAFF2/AMBER-lineage fields expect RESP-fit charges",
    },
}
_HETEROATOMS = ("O", "N", "S", "F", "Cl", "Br", "P", "Si")


def _element_census(smiles: str) -> dict:
    """Crude element count straight off the SMILES string -- no RDKit subprocess.

    Two-letter symbols are matched before one-letter ones so Cl/Br/Si are not miscounted as
    C/B/S. Aromatic lowercase atoms are folded into their uppercase element. This backs D-02's
    backbone_polarity and D-03's backbone_heteroatoms findings, both of which only need
    "are there heteroatoms, and which" -- not a bond-perceived structure.
    """
    counts: dict[str, int] = {}
    for sym in re.findall(r"Cl|Br|Si|[BCNOPSFIbcnops]", smiles):
        el = {"c": "C", "n": "N", "o": "O", "s": "S", "p": "P", "b": "B"}.get(sym, sym)
        counts[el] = counts.get(el, 0) + 1
    return counts


def _electrostatics_guide_rule(rules: dict, polymer_class: str) -> tuple[str, dict]:
    """(rule_name, rule_block) -- whichever of use_lj_cut/use_pppm lists this class."""
    guide = rules.get("electrostatics_decision_guide", {}) or {}
    for name in ("use_lj_cut", "use_pppm"):
        block = guide.get(name) or {}
        if polymer_class.upper() in (block.get("classes") or []):
            return name, block
    return "", {}


def _ev(criterion: str, claim: str, resolver: str, **extra) -> dict:
    """One autofill evidence entry. `origin` is what keeps it out of the LLM-contribution count."""
    out = {"criterion": criterion, "claim": claim, "origin": "autofill", "resolver": resolver}
    out.update({k: v for k, v in extra.items() if v})
    return out


def _d01_ff_row(rules, cls, polymer_class, hw, criteria) -> dict:
    """D-01_ff. evidence_required=true, so at least one entry must carry source_doi/citation."""
    ff = cls.get("preferred_ff")
    ev = []

    # literature_support -- the class's own FF justification, with a real DOI. 7 of 21 classes
    # carry no ff_justification_doi; for those, fall back to the first resolvable citations[] id
    # rather than emitting an uncited claim.
    note = cls.get("ff_note") or f"class default force field for {polymer_class}"
    if cls.get("ff_justification_doi"):
        ev.append(_ev("literature_support",
                      f"polymer_rules.json:classes.{polymer_class}.ff_note: {note}",
                      f"polymer_rules.json:classes.{polymer_class}.ff_justification_doi",
                      source_doi=cls["ff_justification_doi"]))
    else:
        backup = next((sid for sid in (cls.get("citations") or [])
                       if primary_source(rules, sid)), None)
        e = source_evidence(
            rules, backup,
            f"polymer_rules.json:classes.{polymer_class} carries no ff_justification_doi; "
            f"{ff!r} is the class default and the strongest support on file is the class's own "
            f"first cited source. {note}",
            criterion="literature_support",
            resolver=f"polymer_rules.json:classes.{polymer_class}.citations[0]")
        ev.append(e)

    # validation_data -- one entry per cited source, ids resolved to real citations.
    for sid in (cls.get("citations") or []):
        src = primary_source(rules, sid)
        if not src:
            continue
        ev.append(source_evidence(
            rules, sid, src.get("relevance") or f"cited by class {polymer_class}",
            criterion="validation_data",
            resolver=f"polymer_rules.json:_metadata.primary_sources[{sid}]"))

    # parameter_coverage -- the honest gap. Whether this FF can TYPE this repeat unit is not
    # knowable without running forcefield.py select (an EMC trial build per field, minutes).
    ev.append(_ev(
        "parameter_coverage",
        f"NOT MEASURED for this SMILES. forcefield.py select was not run (--with-ff-probe off), "
        f"so coverage is asserted from the class default "
        f"polymer_rules.json:classes.{polymer_class}.preferred_ff={ff!r} only; whether {ff!r} "
        f"can type THIS repeat unit is unverified until the build stage runs.",
        f"polymer_rules.json:classes.{polymer_class}.preferred_ff"))

    # computational_cost -- reuse the D-08 pricing, don't re-call.
    if hw and "error" not in hw:
        est = (hw["decision"]["evidence"] or [{}])[0]
        ev.append(_ev("computational_cost",
                      f"{hw['ff_family']}-family cell of {hw['cell_atoms_estimate']} atoms "
                      f"({hw['cell_mass_g_per_mol_estimate']} g/mol): {est.get('claim', 'unpriced')}. "
                      f"electrostatics={cls.get('electrostatics')}, cutoff_A={cls.get('cutoff_A')}.",
                      "select_hardware.select_hardware"))
    else:
        ev.append(_ev("computational_cost",
                      f"NOT PRICED: select_hardware returned {(hw or {}).get('error', 'no result')}.",
                      "select_hardware.select_hardware"))

    # No class carries forcefield_alternatives (0/21), so there is no deterministic source for
    # an alternative. Say that rather than inventing one or leaving a bare [].
    alts = list(cls.get("forcefield_alternatives") or [])
    if not alts:
        alts = [f"NONE ENUMERATED DETERMINISTICALLY -- polymer_rules.json:classes.{polymer_class} "
                f"has no forcefield_alternatives, and this layer will not invent one. Run with "
                f"--with-ff-probe, or let the literature critic name a candidate."]
    return {"default_choice": ff, "criteria_evaluated": criteria,
            "evidence": ev, "alternatives": alts,
            "resolved_by": f"polymer_rules.json:classes.{polymer_class}.preferred_ff"}


def _d02_charges_row(rules, cls, polymer_class, smiles, criteria) -> dict:
    method = cls.get("charge_method")
    facts = _CHARGE_METHOD_FACTS.get(method, {})
    census = _element_census(smiles) if smiles else {}
    hetero = {el: n for el, n in census.items() if el in _HETEROATOMS}
    rule_name, _ = _electrostatics_guide_rule(rules, polymer_class)

    ev = [
        _ev("backbone_polarity",
            f"Repeat-unit element census from the SMILES: {census or 'unavailable'}; "
            f"heteroatoms present: {hetero or 'none'}. "
            f"polymer_rules.json:electrostatics_decision_guide places {polymer_class} in "
            f"{rule_name or 'neither rule block'}.",
            "make_deterministic_plan._element_census + electrostatics_decision_guide"),
        _ev("charge_method_cost",
            f"charge_method={method!r}: {facts.get('cost', 'cost not characterized for this method')}. "
            f"preferred_builder={cls.get('preferred_builder')}.",
            f"polymer_rules.json:classes.{polymer_class}.charge_method"),
        _ev("ff_embedded_vs_qm",
            f"{method!r} is {'QM-derived' if facts.get('qm') else 'force-field-embedded'}: "
            f"{facts.get('pairing', 'pairing with the chosen FF not characterized')} "
            f"(preferred_ff={cls.get('preferred_ff')!r}).",
            f"polymer_rules.json:classes.{polymer_class}.charge_method"),
    ]
    alts = [f"{m} (not adopted): {f['cost']}"
            for m, f in _CHARGE_METHOD_FACTS.items() if m != method]
    return {"default_choice": method, "criteria_evaluated": criteria,
            "evidence": ev, "alternatives": alts,
            "resolved_by": f"polymer_rules.json:classes.{polymer_class}.charge_method"}


def _d03_electrostatics_row(rules, cls, polymer_class, smiles, hw, criteria) -> dict:
    """D-03. evidence_required=true -- and the old stub's bare `source` key never satisfied it."""
    choice = cls.get("electrostatics")
    rule_name, rule = _electrostatics_guide_rule(rules, polymer_class)
    other_name = "use_pppm" if rule_name == "use_lj_cut" else "use_lj_cut"
    other = (rules.get("electrostatics_decision_guide", {}) or {}).get(other_name, {}) or {}
    census = _element_census(smiles) if smiles else {}
    hetero = {el: n for el, n in census.items() if el in _HETEROATOMS}

    # The guide's rationale strings name their sources inline ("(Afzal2021; Webb2024)");
    # _metadata.primary_sources holds the real DOIs. Join them.
    cited = [sid for sid in ("Afzal2021", "Webb2024") if sid in (rule.get("rationale") or "")]

    ev = []
    e = source_evidence(
        rules, cited[0] if cited else None,
        f"polymer_rules.json:electrostatics_decision_guide places {polymer_class} in "
        f"{rule_name}.classes. Guide criterion: \"{rule.get('criteria', 'n/a')}\" "
        f"Repeat-unit element census: {census or 'unavailable'}; "
        f"heteroatoms: {hetero or 'none'}.",
        criterion="backbone_heteroatoms",
        resolver=f"polymer_rules.json:electrostatics_decision_guide.{rule_name}")
    ev.append(e)

    ev.append(_ev(
        "max_partial_charge",
        f"NOT ASSESSABLE PRE-BUILD. The guide's |q| > 0.1 e threshold is on assigned partial "
        f"charges, which do not exist until the build runs charge_method="
        f"{cls.get('charge_method')!r}. The heteroatom leg of the same criteria clause is "
        f"satisfied independently, so the {choice!r} choice does not rest on this. No value is "
        f"asserted.",
        f"polymer_rules.json:electrostatics_decision_guide.{rule_name}.criteria"))

    cost = (f"Guide rationale: \"{rule.get('rationale', 'n/a')}\" "
            f"Rejected alternative {other_name.replace('use_', '')}: "
            f"\"{other.get('rationale', 'n/a')}\"")
    if hw and "error" not in hw:
        cost += (f" Priced at this run's cell: {hw['cell_atoms_estimate']} atoms, "
                 f"{hw['ff_family']} family.")
    ev.append(source_evidence(
        rules, cited[-1] if cited else None, cost,
        criterion="computational_cost",
        resolver=f"polymer_rules.json:electrostatics_decision_guide.{rule_name}.rationale"))

    alts = [f"{other_name.replace('use_', '')} (rejected): guide criterion is "
            f"\"{other.get('criteria', 'n/a')}\" and lists only "
            f"{', '.join(other.get('classes') or []) or 'no classes'}. "
            f"{polymer_class} does not qualify."] if other else []
    return {"default_choice": choice, "criteria_evaluated": criteria,
            "evidence": ev, "alternatives": alts,
            "resolved_by": f"polymer_rules.json:electrostatics_decision_guide.{rule_name}"}


def _d04_system_size_row(size, hw, criteria) -> dict:
    """D-04. solve_system_size already returns a full decision row -- enrich, don't rebuild."""
    d = size.get("decision", {}) or {}
    ev = []
    for src in (d.get("floor_sources") or []):
        ev.append(_ev("property_target",
                      f"{src.get('source')}: floor_dp={src.get('floor_dp')}",
                      "select_system_size.property_floors"))
    if not ev:
        ev.append(_ev("property_target",
                      "no chain-length floor applies to the requested properties",
                      "select_system_size.property_floors"))

    for entry in (d.get("evidence") or []):
        ev.append(_ev("finite_size_effects", entry.get("claim", ""),
                      "select_system_size.derive_cell",
                      source_doi=SYSTEM_MW_FLOOR_DOI))
    ev.append(_ev("finite_size_effects",
                  "NOT ASSESSED HERE: minimum-image (validate_run_plan._finite_size_findings) "
                  "and chain self-imaging L>=2*Rg (inspect_data_file's finite_size_forecast, "
                  "post-build) are separate, already-mechanized checks.",
                  "select_system_size.solve_system_size"))

    if hw and "error" not in hw:
        est = (hw["decision"]["evidence"] or [{}])[0]
        ev.append(_ev("gpu_budget",
                      f"derived cell = {hw['cell_atoms_estimate']} atoms "
                      f"({hw['cell_mass_g_per_mol_estimate']} g/mol) -> "
                      f"{est.get('claim', 'unpriced')} on {hw['decision']['choice']}",
                      "select_hardware.select_hardware"))
    else:
        ev.append(_ev("gpu_budget",
                      f"NOT PRICED: select_hardware returned {(hw or {}).get('error', 'no result')}.",
                      "select_hardware.select_hardware"))

    alts = list(d.get("alternatives") or [])
    for u in (size.get("uncertainties") or []):
        if u.get("name") == "entanglement_dp_advisory" and u.get("dp_at_me"):
            alts.append(f"DP={u['dp_at_me']} (entanglement Me): considered and NOT adopted -- "
                        "Me gates plateau shear modulus / reptation, not the isothermal bulk "
                        "modulus. Advisory only per decision_policy.json D-04.")
    return {"default_choice": d.get("choice"), "criteria_evaluated": criteria,
            "evidence": ev, "alternatives": alts,
            "resolved_by": "select_system_size.solve_system_size"}


def _d08_hardware_row(rules, cls, hw, criteria) -> dict:
    if not hw or "error" in hw:
        return {"default_choice": None, "criteria_evaluated": criteria,
                "evidence": [_ev("benchmark_evidence",
                                 f"UNRESOLVED: {(hw or {}).get('error', 'no result')}",
                                 "select_hardware.select_hardware")],
                "alternatives": [], "resolved_by": "select_hardware.select_hardware (failed)"}
    d = hw["decision"]
    hp = hardware_policy(rules)
    default = hp.get("by_forcefield", {}).get(hw["ff_family"], {})
    est = (d["evidence"] or [{}])[0]

    gpus = gpu_status()
    load = (", ".join(f"GPU{g['index']}: {g['util']}% util, {g['mem_used_mb']} MiB"
                      for g in gpus)
            if gpus else "nvidia-smi unavailable -- concurrent load UNASSESSED")

    ev = [
        _ev("forcefield_cost_structure",
            f"preferred_ff={cls.get('preferred_ff')!r} resolves to FF family "
            f"{hw['ff_family']!r}; hardware_policy.by_forcefield note: "
            f"{default.get('note', 'none')}",
            "select_hardware.resolve_ff_family + polymer_rules.json:hardware_policy"),
        _ev("atom_count",
            f"cell estimate {hw['cell_atoms_estimate']} atoms at the derived DP/nchain "
            f"({hw['cell_mass_g_per_mol_estimate']} g/mol)",
            "select_hardware.select_hardware"),
        _ev("concurrent_load",
            f"live GPUs at plan time: {load}. This is a plan-time snapshot, not a submit-time "
            "reservation -- hardware_runtime's claim ledger is what actually reserves a GPU.",
            "hardware_runtime.gpu_status"),
        _ev("benchmark_evidence",
            f"{est.get('claim', 'unpriced')}; basis: {est.get('basis', 'n/a')}",
            "select_hardware.estimate_ns_per_day"),
        _ev("cell_size_vs_benchmark_cell",
            f"basis {est.get('basis', 'n/a')} states whether this interpolated within "
            "hardware_policy.directional_probe.size_points or extrapolated beyond them",
            "select_hardware.estimate_ns_per_day"),
        _ev("host_match",
            f"hardware_policy.host {'MATCHES' if host_matches(rules) else 'does NOT match'} "
            "this host; benchmark numbers are "
            f"{'first-party' if host_matches(rules) else 'from a different machine'}",
            "hardware_runtime.host_matches"),
    ]
    alts = ["NONE PRICED -- this repo has no second engine/mpi/gpu configuration with its own "
            "measured ns_per_day to argmin against; see select_hardware.select_hardware's own "
            "note. Pricing an unmeasured config would be fabrication, not selection."]
    return {"default_choice": d["choice"], "criteria_evaluated": criteria,
            "evidence": ev, "alternatives": alts,
            "resolved_by": "select_hardware.select_hardware"}


_DOMINANT_UNCERTAINTY_PRECEDENCE = (
    "ff_transferability", "ff_parameter_provenance", "system_size_chain_length_bias",
    "system_size_mw_floor_unknown", "hardware_optimum", "protocol_transferability",
)


def _dominant_uncertainty(cls, size, hw) -> str:
    names = {u.get("name") for u in (size.get("uncertainties") or [])}
    if not cls.get("ff_justification_doi"):
        return "ff_transferability"
    if "RIGID_BACKBONE_CHAIN_LENGTH_BIAS" in names or "rigid_backbone_chain_length_bias" in names:
        return "system_size_chain_length_bias"
    if size.get("floor_was_unknown") or "MW_FLOOR_UNKNOWN" in names:
        return "system_size_mw_floor_unknown"
    if hw and "error" not in hw and hw["decision"].get("confidence") != "high":
        return "hardware_optimum"
    return "protocol_transferability"


def make_decision(polymer_class: str, smiles: str, properties: set, *,
                   baseline: bool = False) -> dict:
    """The complete deterministic decision for this class + SMILES.

    Costs ~10-20 s: solve_system_size and select_hardware each shell into the RDKit conda env
    for the monomer atom count, and D-08 shells out to nvidia-smi. The old scaffold was instant.
    """
    rules = load_rules()
    if polymer_class.upper() not in rules.get("classes", {}):
        raise ValueError(f"unknown polymer class {polymer_class!r}")
    polymer_class = polymer_class.upper()
    cls = get_class_entry(rules, polymer_class)
    criteria = _policy_criteria()
    resolvers = {}

    # Same argument shape materialize_plan uses, so default_choice and decided_params can't drift.
    try:
        size = solve_system_size(polymer_class, smiles, properties,
                                 dp_typical=None, nchain=None)
        resolvers["select_system_size.solve_system_size"] = "ok"
    except Exception as e:
        size = {}
        resolvers["select_system_size.solve_system_size"] = f"error: {e}"

    rec = size.get("recommended_params", {}) or {}
    sized_cls = {**cls, **rec}
    # Passing the DERIVED dp/nchain is mandatory: select_hardware falls back to
    # cls.get("dp_typical", 50)/cls.get("nchain", 10), and those class keys no longer exist.
    try:
        hw = select_hardware(polymer_class, smiles,
                             sized_cls.get("dp_typical"), sized_cls.get("nchain"))
        resolvers["select_hardware.select_hardware"] = (
            "ok" if "error" not in hw else f"error: {hw['error']}")
    except Exception as e:
        hw = {"error": str(e)}
        resolvers["select_hardware.select_hardware"] = f"error: {e}"
    resolvers["forcefield.select_forcefield"] = "skipped (--with-ff-probe not implemented yet)"

    rows = {
        "D-01_ff": _d01_ff_row(rules, cls, polymer_class, hw, criteria.get("D-01_ff", [])),
        "D-02_charges": _d02_charges_row(rules, cls, polymer_class, smiles,
                                          criteria.get("D-02_charges", [])),
        "D-03_electrostatics": _d03_electrostatics_row(rules, cls, polymer_class, smiles, hw,
                                                        criteria.get("D-03_electrostatics", [])),
        "D-04_system_size": _d04_system_size_row(size, hw, criteria.get("D-04_system_size", [])),
        "D-08_hardware": _d08_hardware_row(rules, cls, hw, criteria.get("D-08_hardware", [])),
    }

    rationale = [
        f"Deterministic decision for {polymer_class} ({smiles}), targeting "
        f"{', '.join(sorted(properties))}. Every row below was resolved by this repo's own "
        f"resolvers, not by an agent; each criterion the matching decision_policy.json policy "
        f"names carries its own evidence entry, including the ones this layer cannot reach.",
    ]
    for rid, row in rows.items():
        gaps = [e["criterion"] for e in row["evidence"]
                if e.get("claim", "").startswith(("NOT MEASURED", "NOT ASSESSABLE",
                                                  "NOT PRICED", "UNRESOLVED"))]
        rationale.append(
            f"{rid} = {row['default_choice']!r} via {row['resolved_by']}. "
            + (f"Unreached criteria for the critic to weigh in on: {', '.join(gaps)}."
               if gaps else "All criteria resolved deterministically."))

    assumptions = [u.get("detail", u.get("name", ""))
                   for u in (size.get("uncertainties") or [])]
    if "error" in (hw or {}):
        assumptions.append(f"D-08 hardware unresolved: {hw['error']}")
    assumptions.append(
        "overrides is deliberately empty: materialize_plan() only auto-fills dp_typical/nchain "
        "for keys overrides does not set, so writing the derived cell here would suppress the "
        "solve it came from.")

    confidence = "unreviewed"
    if baseline:
        confidence = "low"
        rationale.append(
            "BASELINE ARM: confidence stamped 'low' by --baseline so this plan materializes with "
            "no LLM in the loop. This file is the deterministic baseline the LLM arm is measured "
            "against; it carries no literature critique.")

    return {
        "polymer_class": polymer_class,
        "properties": sorted(properties),
        "rationale": rationale,
        "overrides": {},
        "decision_evaluations": rows,
        "assumptions": assumptions,
        "dominant_uncertainty": _dominant_uncertainty(cls, size, hw),
        "confidence": confidence,
        "provenance": {"generator": "make_deterministic_plan.py:decision",
                       "generated_at": datetime.now(timezone.utc).isoformat(),
                       "smiles": smiles,
                       "resolvers": resolvers},
    }


def _properties_from_arg(properties: str) -> set:
    props_str = properties.strip().lower()
    return (set(track_registry.DEFAULT_PROPERTIES) if props_str == "all"
            else {x.strip().lower() for x in props_str.split(",") if x.strip()})


def _cmd_run_plan(args) -> int:
    properties = _properties_from_arg(args.properties)
    cache_path = Path(args.cache_path) if args.cache_path else None
    plan = (_try_cache(args.run_name, args.polymer_class, args.smiles, properties, cache_path)
            or make_plan(args.run_name, args.polymer_class, args.smiles, properties))
    text = json.dumps(plan, indent=2)

    if args.out == "-":
        print(text)
        return 0
    out_path = (Path(args.out) if args.out
                else REPO_ROOT / "data" / args.run_name / "raw" / "run_plan.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(json.dumps({"status": "success", "run_plan": str(out_path),
                      "plan_mode": plan["plan_mode"], "confidence": plan["confidence"]}))
    return 0


def _cmd_decision(args) -> int:
    properties = _properties_from_arg(args.properties)
    decision = make_decision(args.polymer_class, args.smiles, properties,
                             baseline=args.baseline)
    text = json.dumps(decision, indent=2)

    if args.out == "-":
        print(text)
        return 0
    out_path = (Path(args.out) if args.out
                else REPO_ROOT / "data" / args.run_name / "raw" / "decision.json")
    if out_path.exists() and not args.force:
        print(json.dumps({
            "status": "error",
            "error": f"{out_path} already exists; pass --force to overwrite (this destroys "
                     "any annotation already written)",
        }), file=sys.stderr)
        return 1
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(json.dumps({"status": "success", "decision_file": str(out_path),
                      "decision_ids": sorted(decision["decision_evaluations"]),
                      "confidence": decision["confidence"],
                      "resolvers": decision["provenance"]["resolvers"]}))
    return 0


def main():
    p = argparse.ArgumentParser(description="Emit the deterministic planning artifacts.")
    sub = p.add_subparsers(dest="command", required=True)

    def _common(sp):
        sp.add_argument("--run_name")
        sp.add_argument("--polymer_class", required=True)
        sp.add_argument("--smiles", default=None)
        sp.add_argument("--properties", default="all",
                        help="Comma-separated: density,tg,bulk_modulus or 'all'")
        sp.add_argument("--out", default=None, help="Output path; '-' = stdout")
        return sp

    rp = _common(sub.add_parser("run-plan", help="emit run_plan.json"))
    rp.add_argument("--cache_path", default=None,
                    help="Override guides/system_characterization_cache.json path (testing only)")
    rp.set_defaults(func=_cmd_run_plan)

    dc = _common(sub.add_parser("decision", help="emit the fully-resolved decision.json"))
    dc.add_argument("--force", action="store_true",
                    help="Overwrite an existing decision.json (default: refuse, to protect "
                         "in-progress critique work)")
    dc.add_argument("--baseline", action="store_true",
                    help="Stamp confidence='low' instead of 'unreviewed', so the plan "
                         "materializes with no LLM in the loop. For the deterministic benchmark "
                         "arm only -- a normal reasoned run leaves this off and the literature "
                         "critic's review sets the confidence.")
    dc.set_defaults(func=_cmd_decision)

    args = p.parse_args()
    if not args.run_name:
        p.error("--run_name is required")
    # `decision` resolves the cell and the hardware from the molecule itself, so the SMILES is
    # load-bearing there. `run-plan` still tolerates None (cache replay / class-default path).
    if args.command == "decision" and not args.smiles:
        p.error("--smiles is required for `decision`: D-01/D-02/D-03/D-04/D-08 are all resolved "
                "per-molecule, not per-class")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
