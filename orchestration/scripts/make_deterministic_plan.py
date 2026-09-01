#!/usr/bin/env python3
"""
make_deterministic_plan.py — Emit a deterministic run_plan.json for a polymer class.

This is the class-default plan materializer used by the scientific control layer. It transcribes
decision-relevant defaults from guides/polymer_rules.json into a structured plan scaffold. The
scientific planning agent chooses the class, properties, evidence, and bounded overrides before
the scaffold becomes executable.

Reproducibility guarantee: decided_params snapshots ONLY keys already present in
the class entry, with their existing values. stage_params.py overlays them as
{**cls, **decided_params}, which is therefore an identity for an unmodified scaffold.

`scientific_control.py` turns this scaffold into a reasoned plan and records the agent's
rationale, evidence, uncertainty, confidence, and decision digest.

Usage:
  python3 orchestration/make_deterministic_plan.py \
      --run_name PE7 --polymer_class PHYC \
      [--smiles "*CC*"] [--properties density,tg,bulk_modulus] \
      [--out PATH]        # default: data/<run_name>/raw/run_plan.json; "-" = stdout
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import load_rules, get_class_entry, hardware_policy, resolve_ff_family  # shared rules access (single source of truth)
import track_registry  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from stage_params import _exp_tg_point, _regime_exp_tg  # reuse the proven resolvers, don't duplicate them
import canon_smiles  # noqa: E402  -- module import so tests can monkeypatch canon_smiles.canonicalize

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


def build_decisions(cls: dict) -> list:
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
         "choice": f"DP={cls.get('dp_typical')}, nchain={cls.get('nchain')}",
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
        "decisions": build_decisions(cls),
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
        canonical = canon_smiles.canonicalize(smiles, isomeric=True)
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


def main():
    p = argparse.ArgumentParser(description="Emit a deterministic run_plan.json.")
    p.add_argument("--run_name")
    p.add_argument("--polymer_class", required=True)
    p.add_argument("--smiles", default=None)
    p.add_argument("--properties", default="all",
                   help="Comma-separated: density,tg,bulk_modulus or 'all'")
    p.add_argument("--out", default=None,
                   help="Output path; default data/<run_name>/raw/run_plan.json; '-' = stdout")
    p.add_argument("--cache_path", default=None,
                   help="Override guides/system_characterization_cache.json path (testing only)")
    args = p.parse_args()

    if not args.run_name:
        p.error("--run_name is required")

    props_str = args.properties.strip().lower()
    properties = (set(track_registry.VALID_PROPERTIES) if props_str == "all"
                  else {x.strip().lower() for x in props_str.split(",") if x.strip()})

    cache_path = Path(args.cache_path) if args.cache_path else None
    plan = (_try_cache(args.run_name, args.polymer_class, args.smiles, properties, cache_path)
            or make_plan(args.run_name, args.polymer_class, args.smiles, properties))
    text = json.dumps(plan, indent=2)

    if args.out == "-":
        print(text)
        return
    out_path = (Path(args.out) if args.out
                else REPO_ROOT / "data" / args.run_name / "raw" / "run_plan.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    print(json.dumps({"status": "success", "run_plan": str(out_path),
                      "plan_mode": plan["plan_mode"], "confidence": plan["confidence"]}))


if __name__ == "__main__":
    main()
