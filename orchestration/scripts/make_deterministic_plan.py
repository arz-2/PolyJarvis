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
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import load_rules, get_class_entry  # shared rules access (single source of truth)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# Decision-relevant class keys consumed by stage_params.py. Only keys that
# EXIST in the class entry are snapshotted, so the overlay stays an exact identity.
SNAPSHOT_KEYS = [
    "preferred_ff", "preferred_builder", "charge_method", "electrostatics",
    "cutoff_A", "dt_fs",
    "dp_typical", "nchain", "density_initial_gcm3",
    "T_equil_K", "annealing_T_high_K", "P_equil_atm", "eq_annealing_cycles",
    "t_equil_ns", "npt_prod_ns", "melt_npt_ns",
    "tg_t_high_K", "tg_t_low_K", "tg_t_step_K", "tg_steps_per_t", "tg_rates_K_per_ns",
    "tg_min_steps_per_T", "tg_slope_gate_fallback",
    "K_deform_rate_inv_s", "K_deform_rate_slow_inv_s", "K_strain_max",
    "bm_pressures_atm", "ct_min_decay_melt",
    "alpha_glass_per_K", "alpha_melt_per_K",
]


def _exp_tg_scalar(cls: dict):
    """Tg used ONLY for the glassy-vs-rubbery REGIME (and hence equil temperature). For a
    multi-member class the members sit on the same side of 300 K, so the dict median picks the
    regime correctly — keep it, so the deterministic plan reproduces the no-plan equil prompt."""
    tg = cls.get("experimental_tg_K")
    if isinstance(tg, dict):
        vals = sorted(v for v in tg.values() if isinstance(v, (int, float)))
        return vals[len(vals) // 2] if vals else None
    return tg if isinstance(tg, (int, float)) else None


def _exp_tg_bracket(cls: dict):
    """Tg ACCURACY success_criterion (t_range_brackets_exp_tg). A multi-member dict has no
    SMILES->member mapping, so the scaffold cannot tell which member this run is — leave the
    bracket UNPINNED (None) rather than silently picking a wrong member (the old median pick
    gave PEKK/433 for a PEEK/418 run). The planner must pin the member from the SMILES (see each
    class's experimental_tg_K.multi_member_note in polymer_rules.json). Single-member passes through."""
    tg = cls.get("experimental_tg_K")
    return tg if isinstance(tg, (int, float)) else None


def build_decisions(cls: dict) -> list:
    """Structured default decision rows carrying evidence/confidence/alternatives, mirroring
    run_summary.json decision IDs. Evidence is transcribed from existing class fields.

    "confidence" here is a fixed "class_default" placeholder. The scientific control layer
    replaces it with the planning agent's confidence before execution.
    """
    ff_evidence = []
    if cls.get("ff_justification_doi"):
        ff_evidence.append({"claim": cls.get("ff_note", "force field choice"),
                            "source_doi": cls.get("ff_justification_doi")})
    for cit in cls.get("citations", []):
        ff_evidence.append({"claim": "supporting validation", "citation": cit})

    conf = "class_default"
    return [
        {"id": "D-01_ff", "choice": cls.get("preferred_ff"),
         "criteria_evaluated": ["literature_support", "parameter_coverage",
                                 "validation_data", "computational_cost"],
         "evidence": ff_evidence, "confidence": conf,
         "alternatives": cls.get("forcefield_alternatives", [])},
        {"id": "D-02_charges", "choice": cls.get("charge_method"),
         "criteria_evaluated": ["backbone_polarity", "ff_embedded_vs_qm"],
         "evidence": [], "confidence": conf, "alternatives": []},
        {"id": "D-03_electrostatics", "choice": cls.get("electrostatics"),
         "criteria_evaluated": ["backbone_heteroatoms", "max_partial_charge"],
         "evidence": [{"claim": "see electrostatics_decision_guide",
                       "source": "polymer_rules.json:electrostatics_decision_guide"}],
         "confidence": conf, "alternatives": []},
        {"id": "D-04_system_size",
         "choice": f"DP={cls.get('dp_typical')}, nchain={cls.get('nchain')}",
         "criteria_evaluated": ["property_target", "finite_size_effects", "gpu_budget"],
         "evidence": [], "confidence": conf, "alternatives": []},
    ]


STAGE_TRACK = {
    "build":       "foundation",
    "equil":       "foundation",
    "equil-check": "foundation",
    "tg":          "thermal",
    "analyze-tg":  "thermal",
    "deform":      "mechanical",
    "murnaghan":   "mechanical",
    "analyze-bm":  "mechanical",
    "run-summary": "summary",
}


def build_planned_stages(cls: dict, properties: set) -> list:
    """Experiment DAG with per-stage success_criteria the Validator enforces."""
    exp_tg = _exp_tg_scalar(cls)                 # regime/temperature (median ok for multi-member)
    glassy_hint = (exp_tg is not None and exp_tg > 300)
    exp_tg_bracket = _exp_tg_bracket(cls)        # accuracy gate (None for multi-member → planner pins)

    def _s(stage, criteria, **extra):
        return {"stage": stage, "track": STAGE_TRACK[stage],
                "success_criteria": criteria, **extra}

    stages = [
        _s("build",       {"data_file_written": True}),
        _s("equil",       {"check_equilibration_comprehensive.overall_pass": True}),
        _s("equil-check", {"equil_verdict": "PASS"}),
    ]
    if "tg" in properties:
        # Single-rate-primary: one sweep at the class's primary configured rate (highest by
        # default; tg_slope_gate_fallback="slowest_rate" classes run rates[0] instead — their
        # highest-rate fit is documented as degenerate/inverted).
        stages.append(_s("tg", {"bilinear_fit_r_squared_min": 0.80,
                                "t_range_brackets_exp_tg": exp_tg_bracket}))
        stages.append(_s("analyze-tg", {}))
    if "bulk_modulus" in properties:
        # Murnaghan always submits now (2026-08-09): guides/MURNAGHAN.md's rubbery
        # null-fallback resolves to the PROBE ladder instead of an all-null RESULT, so
        # there is no longer a "rubbery without pressures -> fluctuation only, no submit
        # stage" case. Glassy still carries the deform fallback; rubbery (empirical
        # ladder or PROBE ladder) does not.
        stages.append(_s("murnaghan", {"chain_submitted": True},
                          **({"fallback": "deform"} if glassy_hint else {})))
        stages.append(_s("analyze-bm", {}))
    stages.append(_s("run-summary", {}))  # always terminal
    return stages


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
    exp_tg = _exp_tg_scalar(cls)
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
        "planned_stages": build_planned_stages(cls, properties),
        "critique": {"status": "pending_scientific_review", "rounds": 0, "findings": []},
        "provenance": {"generator": "make_deterministic_plan.py",
                       "generated_at": datetime.now(timezone.utc).isoformat()},
    }


def main():
    p = argparse.ArgumentParser(description="Emit a deterministic run_plan.json.")
    p.add_argument("--run_name")
    p.add_argument("--polymer_class", required=True)
    p.add_argument("--smiles", default=None)
    p.add_argument("--properties", default="all",
                   help="Comma-separated: density,tg,bulk_modulus or 'all'")
    p.add_argument("--out", default=None,
                   help="Output path; default data/<run_name>/raw/run_plan.json; '-' = stdout")
    args = p.parse_args()

    if not args.run_name:
        p.error("--run_name is required")

    props_str = args.properties.strip().lower()
    properties = ({"density", "tg", "bulk_modulus"} if props_str == "all"
                  else {x.strip().lower() for x in props_str.split(",") if x.strip()})

    plan = make_plan(args.run_name, args.polymer_class, args.smiles, properties)
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
