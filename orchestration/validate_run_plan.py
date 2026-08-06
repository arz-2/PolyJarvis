#!/usr/bin/env python3
"""
validate_run_plan.py — mechanical structural checks for a run_plan.json against
decision_policy.json, extracted from critic.md step 3.

Covers only what's actually mechanical: criteria-coverage (criteria_evaluated ⊇ the matching
policy's evaluate list), evidence_required presence, stage schema (required fields / valid
track / stage->track mapping), loose stage-vs-properties coverage, dominant-uncertainty
naming, reduction_probe validity, and the arithmetic/require-clause parts of D-08 hardware
safety (delegated to select_hardware.py so the numbers live in exactly one place).

Deliberately NOT covered (stays critic.md prose, per its own step 3): whether cited evidence
substantively supports its claim, directional-probe "evidence inconsistency" judgment calls,
the "no boilerplate bounce" carve-out (a finding here tagged severity=advisory may still be a
legitimate approve — critic.md decides), and verdict/escalation sequencing.

planner.md also calls this as a self-check before finalizing a reasoned plan, to catch schema
mistakes before they cost a critic round-trip.

Usage:
  python3 orchestration/validate_run_plan.py --run_plan data/<RUN>/raw/run_plan.json
Prints a JSON object {"findings": [...]} to stdout (exit 0 always -- findings is the payload,
not an error signal; a non-empty list is not itself a failure, see severity per finding).
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from select_hardware import select_hardware

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = REPO_ROOT / "orchestration" / "decision_policy.json"


def _criteria_and_evidence_findings(plan: dict, policy: dict) -> list:
    findings = []
    policies_by_decision_id = {p["decision_id"]: p for p in policy.get("policies", {}).values()}
    for d in plan.get("decisions", []):
        pol = policies_by_decision_id.get(d.get("id"))
        if not pol:
            continue
        missing = set(pol.get("evaluate", [])) - set(d.get("criteria_evaluated", []))
        if missing:
            findings.append({"check": "criteria_coverage", "decision_id": d["id"],
                             "severity": "structural",
                             "detail": f"missing criteria_evaluated: {sorted(missing)}"})
        if pol.get("evidence_required"):
            ev = d.get("evidence", [])
            if not any(("source_doi" in e or "citation" in e) for e in ev):
                findings.append({"check": "evidence_required", "decision_id": d["id"],
                                 "severity": "structural",
                                 "detail": "evidence_required policy but no evidence entry "
                                           "has source_doi/citation"})
            if not d.get("alternatives"):
                findings.append({"check": "alternatives_empty", "decision_id": d["id"],
                                 "severity": "advisory",
                                 "detail": "evidence_required decision has empty alternatives "
                                           "-- critic.md's no-boilerplate-bounce carve-out may "
                                           "apply for a carried-over validated default; judge "
                                           "in context, do not auto-revise on this alone"})
    return findings


def _stage_schema_findings(plan: dict, policy: dict) -> list:
    findings = []
    ssr = policy["stage_schema_requirements"]
    for s in plan.get("planned_stages", []):
        missing = [f for f in ssr["required_fields"] if f not in s]
        if missing:
            findings.append({"check": "stage_schema", "stage": s.get("stage"),
                             "severity": "structural", "detail": f"missing fields {missing}"})
            continue
        if s["track"] not in ssr["valid_tracks"]:
            findings.append({"check": "stage_schema", "stage": s["stage"], "severity": "structural",
                             "detail": f"invalid track {s['track']!r}"})
        expected = ssr["track_map"].get(s["stage"])
        if expected and s["track"] != expected:
            findings.append({"check": "stage_schema", "stage": s["stage"], "severity": "structural",
                             "detail": f"track {s['track']!r} != expected {expected!r} "
                                       f"for stage {s['stage']!r}"})
    return findings


def _stage_properties_findings(plan: dict) -> list:
    findings = []
    stages_present = {s.get("stage") for s in plan.get("planned_stages", [])}
    props = set(plan.get("properties", []))
    for base in ("build", "equil", "equil-check", "run-summary"):
        if base not in stages_present:
            findings.append({"check": "stage_properties", "severity": "structural",
                             "detail": f"missing always-required stage {base!r}"})
    if "tg" in props and not (stages_present & {"tg", "analyze-tg", "analyze-tg-multirate"}):
        findings.append({"check": "stage_properties", "severity": "structural",
                         "detail": "tg requested but no tg/analyze-tg stage present"})
    if "bulk_modulus" in props and not (stages_present & {"murnaghan", "deform", "analyze-bm"}):
        findings.append({"check": "stage_properties", "severity": "structural",
                         "detail": "bulk_modulus requested but no murnaghan/deform/analyze-bm "
                                   "stage present"})
    return findings


def _uncertainty_findings(plan: dict, policy: dict) -> list:
    findings = []
    uncs = plan.get("uncertainties", [])
    if uncs and not any(u.get("dominant") and u.get("name") for u in uncs):
        findings.append({"check": "dominant_uncertainty", "severity": "structural",
                         "detail": "no uncertainties[] entry has dominant=true with a name"})
    valid_probes = set(policy.get("uncertainty_reduction_probes", {}).keys()) - {"description"}
    for u in uncs:
        rp = u.get("reduction_probe")
        if rp and rp != "none" and rp not in valid_probes:
            findings.append({"check": "reduction_probe", "severity": "structural",
                             "detail": f"unknown reduction_probe {rp!r} on uncertainty "
                                       f"{u.get('name')!r}"})
    return findings


def _hardware_findings(plan: dict) -> list:
    """Delegates the recommended choice to select_hardware.py -- decision_policy.json's
    hardware require/prefer thresholds live there once, not duplicated here."""
    findings = []
    dp = plan.get("decided_params", {})
    pin = {k: dp.get(k) for k in ("engine", "gpu_per_run", "mpi_ranks")}
    if not any(pin.values()):
        return findings  # unpinned -> runtime by_forcefield fallback, always safe

    smiles = plan.get("smiles")
    polymer_class = plan.get("polymer_class")
    if not smiles or not polymer_class:
        findings.append({"check": "hardware_safety", "severity": "structural",
                         "detail": "decided_params pins hardware but plan is missing "
                                   "smiles/polymer_class -- cannot verify"})
        return findings

    try:
        rec = select_hardware(polymer_class, smiles, dp.get("dp_typical"), dp.get("nchain"))
    except Exception as e:
        findings.append({"check": "hardware_safety", "severity": "structural",
                         "detail": f"select_hardware.py raised: {e}"})
        return findings
    if "error" in rec:
        findings.append({"check": "hardware_safety", "severity": "structural",
                         "detail": f"select_hardware.py error: {rec['error']}"})
        return findings

    rec_choice = rec["decision"]["choice"]
    d08 = next((d for d in plan.get("decisions", []) if d.get("id") == "D-08_hardware"), None)

    if pin.get("mpi_ranks") == 1 and pin.get("engine") == "gpu" and rec["ff_family"] != "trappe":
        findings.append({"check": "hardware_anti_pattern", "severity": "structural",
                         "detail": "mpi_ranks=1 with engine=gpu (GPU package, not kokkos) "
                                   "starves PPPM kspace -- policy requires mpi>=4 there "
                                   "(decision_policy.json:policies.hardware.require)"})

    gpu_pin = pin.get("gpu_per_run") or 1
    if gpu_pin >= 2:
        if rec["cell_atoms_estimate"] < 10000:
            findings.append({"check": "hardware_size_mismatch", "severity": "structural",
                             "detail": f"gpu_per_run={gpu_pin} pinned but estimated cell "
                                       f"{rec['cell_atoms_estimate']} atoms < 10k"})
        elif rec["decision"]["confidence"] != "high":
            findings.append({"check": "hardware_size_mismatch", "severity": "structural",
                             "detail": "gpu_per_run>=2 pinned without clean benchmark support "
                                       "(select_hardware.py would not recommend it at high "
                                       "confidence for this cell/host)"})

    deviates = any(pin.get(k) not in (None, rec_choice.get(k)) for k in rec_choice)
    if deviates:
        if d08 is None:
            findings.append({"check": "hardware_missing_decision", "severity": "structural",
                             "detail": "decided_params pins non-default hardware but no "
                                       "D-08_hardware entry in decisions[]"})
        elif d08.get("confidence") != "low" and rec["decision"]["confidence"] != "high":
            findings.append({"check": "hardware_staleness", "severity": "structural",
                             "detail": f"pin {pin} deviates from the policy-recommended "
                                       f"{rec_choice} without confidence:low on D-08_hardware "
                                       "(not cleanly benchmarked on this host/cell size)"})
    return findings


def validate_plan(plan: dict, policy: dict) -> list:
    findings = []
    findings += _criteria_and_evidence_findings(plan, policy)
    findings += _stage_schema_findings(plan, policy)
    findings += _stage_properties_findings(plan)
    findings += _uncertainty_findings(plan, policy)
    findings += _hardware_findings(plan)
    return findings


def main():
    p = argparse.ArgumentParser(description="Mechanical structural checks for a run_plan.json.")
    p.add_argument("--run_plan", required=True, metavar="RUN_PLAN_JSON")
    p.add_argument("--policy", default=str(POLICY_PATH))
    args = p.parse_args()

    plan = json.loads(Path(args.run_plan).read_text())
    policy = json.loads(Path(args.policy).read_text())
    findings = validate_plan(plan, policy)
    print(json.dumps({"findings": findings, "count": len(findings)}, indent=2))


if __name__ == "__main__":
    main()
