#!/usr/bin/env python3
"""
validate_run_plan.py — mechanical structural checks for a run_plan.json against
decision_policy.json.

Covers only what's actually mechanical: criteria-coverage (criteria_evaluated ⊇ the matching
policy's evaluate list), evidence_required presence, stage schema (required fields / valid
track / stage->track mapping), loose stage-vs-properties coverage, dominant-uncertainty
naming, reduction_probe validity, and the arithmetic/require-clause parts of D-08 hardware
safety (delegated to select_hardware.py so the numbers live in exactly one place).

Substantive scientific support remains the planning agent's responsibility. The deterministic
control plane blocks on structural findings and preserves advisory findings in control-state
provenance.

Usage:
  python3 orchestration/validate_run_plan.py --run_plan data/<RUN>/raw/run_plan.json
Prints a JSON object {"findings": [...]} to stdout (exit 0 always -- findings is the payload,
not an error signal; a non-empty list is not itself a failure, see severity per finding).
"""
import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from select_hardware import select_hardware
from select_system_size import select_system_size
from hw_common import load_rules, get_class_entry, hardware_policy, host_matches

_ENGINE_SCRIPTS = (Path(__file__).resolve().parents[2]
                   / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts")
if str(_ENGINE_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_ENGINE_SCRIPTS))
from finite_size import predict_equilibrated_L  # noqa: E402


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
POLICY_PATH = REPO_ROOT / "orchestration" / "decision_policy.json"

# Finite-size forecast target density: density_initial_gcm3 is a build parameter chosen for
# every run (how loosely to pack the initial cell before EMC/LAMMPS compress it), never
# experimental data -- always resolvable, unlike a curated per-SMILES experimental_density_gcm3.
# See orchestration/scripts/run_campaign.py's COMPRESSION_RATIO for the same constant/rationale
# (duplicated, not shared -- no existing shared-constants module for this kind of value).
COMPRESSION_RATIO = 2.0


def _prefix(decision_id: str) -> str:
    """'D-06_tg_ladder' -> 'D-06'."""
    return decision_id.split("_", 1)[0] if decision_id else ""


def _criteria_and_evidence_findings(plan: dict, policy: dict) -> list:
    findings = []
    policies_by_decision_id = {p["decision_id"]: p for p in policy.get("policies", {}).values()}
    policies_by_prefix = {}
    for did, p in policies_by_decision_id.items():
        policies_by_prefix.setdefault(_prefix(did), []).append((did, p))

    for d in plan.get("decisions", []):
        d_id = d.get("id", "")
        pol = policies_by_decision_id.get(d_id)
        if not pol:
            # Check A: unique D-0N-prefix match still gets evaluated (no silent skip),
            # flagged advisory.
            candidates = policies_by_prefix.get(_prefix(d_id), [])
            if len(candidates) != 1:
                continue
            cand_id, pol = candidates[0]
            findings.append({"check": "decision_id_drift", "decision_id": d_id,
                             "severity": "advisory",
                             "detail": f"id {d_id!r} != policy decision_id {cand_id!r} "
                                       "(same D-0N prefix) -- evaluated anyway, ids should agree"})
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
                                           "-- the planning agent should record alternatives "
                                           "when scientifically meaningful"})
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
    if "tg" in props and not (stages_present & {"tg", "analyze-tg"}):
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


def _exp_tg_companion_findings(plan: dict) -> list:
    """Check C: a tg stage's t_range_brackets_exp_tg is the pinned experimental Tg target
    (a number) once build_planned_stages resolves it via run_name -- None means it genuinely
    never resolved (run_name didn't match any member of a multi-member experimental_tg_K dict,
    or no run_name was available, e.g. the scaffold path). Flag that unresolved case: without a
    pinned target, the tg stage's accuracy gate has nothing to check the sweep range against.

    (Previously this tested `is True`, a value build_planned_stages could never produce --
    the field has only ever held a number or None -- so this check could never fire for any
    plan, single- or multi-member.)"""
    findings = []
    for s in plan.get("planned_stages", []):
        if s.get("stage") != "tg":
            continue
        sc = s.get("success_criteria", {})
        if "t_range_brackets_exp_tg" in sc and sc.get("t_range_brackets_exp_tg") is None:
            findings.append({"check": "exp_tg_companion", "stage": "tg", "severity": "advisory",
                             "detail": "t_range_brackets_exp_tg is unresolved (None) -- no "
                                       "pinned experimental Tg target for this run's member"})
    return findings


def _tg_window_ceiling_findings(plan: dict) -> list:
    """A hand-set Tg sweep window must be accompanied by an anneal ceiling that clears it.

    The thermal stage starts its staircase from a cell the equilibration cooldown already
    wrote -- cool_block saves a .data file at every waypoint between the anneal ceiling and
    final_T_K -- so one of those waypoints has to sit at or above tg_t_high_K. One cool block
    of headroom is needed, not zero: the ceiling itself is only reached by anneal_hold, which
    runs NVT and therefore still carries the densified 300 K volume rather than a melt density.

    temperature_schedule raises the ceiling automatically for a DERIVED window, which is a pure
    function of the SMILES and hence already build-hashed. It deliberately does NOT do so for an
    EXPLICIT tg_t_high_K override: that key hashes to the THERMAL stage
    (workflow_engine.PARAMETER_STAGE), so propagating it into the ceiling would rewrite the
    equilibration chain under an unchanged equilibration _input_hash -- a store would then serve
    one run's equilibrated cell for another's. The override is honoured for the sweep and
    flagged here instead, so the plan raises annealing_T_high_K (equilibration-hashed, and
    therefore an honest invalidation) in the same edit.

    Advisory, not structural: the run still executes. It just reheats the finished final_T_K
    cell to reach the sweep top instead of starting from a melt-cooled one, which biases the
    rubbery branch of the fit and hence the breakpoint.
    """
    decided = plan.get("decided_params") or {}
    if "tg_t_high_K" not in decided:
        return []
    tg_high = decided.get("tg_t_high_K")
    ceiling = decided.get("annealing_T_high_K")
    if not isinstance(tg_high, (int, float)) or not isinstance(ceiling, (int, float)):
        return []
    headroom = decided.get("cool_block_dT_K") or 25.0
    if tg_high + headroom <= ceiling:
        return []
    return [{"check": "tg_window_ceiling", "stage": "tg", "severity": "advisory",
             "detail": (f"explicit tg_t_high_K={tg_high} K needs annealing_T_high_K of at least "
                        f"{tg_high + headroom} K (sweep top + one cool block of "
                        f"{headroom} K), have {ceiling} K -- the cooldown never writes a cell "
                        f"at the sweep's start, so the thermal stage will reheat the "
                        f"final_T_K cell instead of starting from a melt-cooled one")}]


def _finite_size_findings(plan: dict) -> list:
    """Cheapest possible finite-size check: plan time, before the build, before any GPU.

    Only the MINIMUM-IMAGE criterion is decidable here -- it needs no Rg. The predicted
    equilibrated box edge follows from the planned cell mass and an estimated target density:
    L = (m / (N_A * rho))^(1/3), where rho = COMPRESSION_RATIO * density_initial_gcm3 -- never
    a curated experimental value (a novel system may have none), always resolvable since
    density_initial_gcm3 is a build parameter chosen for every run, not measured data.

    The chain-self-imaging criterion (L >= 2*Rg) needs a real Rg, so it is enforced one
    step later by inspect_data_file's finite_size_forecast on the built cell -- still
    before any MD. This function only notes that it is pending, so a plan is never
    approved believing the size question is fully settled here.
    """
    findings = []
    dp = plan.get("decided_params", {})
    smiles, polymer_class = plan.get("smiles"), plan.get("polymer_class")
    if not smiles or not polymer_class:
        return findings

    cls = get_class_entry(load_rules(), polymer_class) or {}
    cutoff_A = dp.get("cutoff_A") or cls.get("cutoff_A")
    rho = COMPRESSION_RATIO * (dp.get("density_initial_gcm3") or cls.get("density_initial_gcm3", 0.6))
    if not cutoff_A or not rho:
        return findings

    try:
        rec = select_hardware(polymer_class, smiles, dp.get("dp_typical"), dp.get("nchain"))
        cell_mass = rec.get("cell_mass_g_per_mol_estimate")
    except Exception:
        return findings
    if not cell_mass:
        return findings

    L_pred = predict_equilibrated_L(cell_mass, rho)
    if L_pred is None:
        return findings

    if L_pred < 2.0 * cutoff_A:
        nchain = dp.get("nchain") or cls.get("nchain")
        factor = ((2.0 * cutoff_A) / L_pred) ** 3
        suggest = f" Raise nchain by x{factor:.2f}"
        if nchain:
            suggest += f" (>= {math.ceil(nchain * factor)})"
        findings.append({
            "check": "finite_size_min_image", "severity": "structural",
            "detail": (f"predicted equilibrated box L={L_pred:.1f} A (cell mass "
                       f"{cell_mass:.0f} g/mol at {rho} g/cm3) < 2*cutoff_A="
                       f"{2 * cutoff_A:.1f} A. Atoms would interact with their own periodic "
                       f"images -- the pair potential itself would be wrong."
                       f"{suggest}. Do not build this plan.")})
    else:
        findings.append({
            "check": "finite_size_min_image", "severity": "info",
            "detail": (f"minimum image OK: predicted L={L_pred:.1f} A vs 2*cutoff_A="
                       f"{2 * cutoff_A:.1f} A (ratio {L_pred / (2 * cutoff_A):.2f}). "
                       "Chain self-imaging (L >= 2*Rg) needs a measured Rg and is enforced "
                       "by inspect_data_file on the built cell, before any MD.")})
    return findings


def _family_has_multi_gpu_benchmark(fam: str) -> bool:
    """True iff some real measured point for this FF family (recommended_by_ff or
    size_points) actually used gpu_per_run>=2 ON A HOST MATCHING THIS ONE
    (hw_common.host_matches -- hardware_policy.host, the same host-match check
    cost_model.estimate_ns_per_day itself uses). Every point calibrated so far (both fields)
    is gpu=1 -- select_hardware.py's cost_model-driven "high" confidence describes how well
    the ns_per_day NUMBER at a given atom count is supported, not whether a >=2-GPU pin is
    benchmarked, which is what this specific check claims to verify -- those are different
    claims and must not be conflated just because one confidence field happens to cover both
    today."""
    rules = load_rules()
    if not host_matches(rules):
        return False
    dp_probe = hardware_policy(rules).get("directional_probe", {})
    rec = dp_probe.get("recommended_by_ff", {}).get(fam)
    if rec and (rec.get("gpu") or 1) >= 2:
        return True
    return any((p.get("gpu") or 1) >= 2 for p in dp_probe.get("size_points", {}).get(fam, []))


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
        elif not _family_has_multi_gpu_benchmark(rec["ff_family"]):
            findings.append({"check": "hardware_size_mismatch", "severity": "structural",
                             "detail": f"gpu_per_run={gpu_pin} pinned for ff_family="
                                       f"{rec['ff_family']!r} but no real measured point "
                                       "(recommended_by_ff or size_points) for this family "
                                       "used gpu_per_run>=2 -- a well-supported ns_per_day "
                                       "number at gpu=1 is not evidence for a multi-GPU pin"})

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


# Parameters may be listed here only after a complete plan→resolver→executor trace proves
# that the declared value cannot affect a generated deck. Keep the map empty while every
# currently advertised planning parameter has an executable consumer.
UNIMPLEMENTED_PARAMS = {}


# decided_params that ARE wired, but that another decided_param silently overrides. The plan
# then records a protocol the deck did not run. Keyed by the overridden param; the value is
# (overriding param, why).
OVERRIDDEN_PARAMS = {
    "tg_steps_per_t": ("tg_rate_index",
                       "stage_params._resolve_tg_params computes n_steps_per_t from the selected "
                       "cooling rate (T_step / (rate*dt)) whenever a rate index is given, and "
                       "ignores tg_steps_per_t entirely"),
}


def _overridden_param_findings(plan: dict) -> list:
    """A recorded value the deck silently replaced is a false protocol record.

    Info rather than structural: the executed deck is correct (the rate is the governing knob),
    but the plan must not claim a step count that did not run.
    """
    findings = []
    dp = plan.get("decided_params", {})
    for key, (overrider, why) in sorted(OVERRIDDEN_PARAMS.items()):
        if dp.get(key) in (None, "null") or dp.get(overrider) in (None, "null"):
            continue
        findings.append({
            "check": "decided_param_overridden", "severity": "info",
            "detail": (f"decided_params.{key}={dp[key]} is recorded but {overrider}="
                       f"{dp[overrider]} overrides it: {why}. Drop {key} from the plan so the "
                       "record matches the deck.")})
    return findings


def _unimplemented_param_findings(plan: dict) -> list:
    """A parameter that cannot reach the deck must not be usable as a remedy lever.

    This fires structural rather than info because the failure is silent in both
    directions: the plan records a protocol that was not run, and a gate-driven fix
    written here produces no change in behaviour to explain why it did not work.
    """
    findings = []
    dp = plan.get("decided_params", {})
    for key, why in sorted(UNIMPLEMENTED_PARAMS.items()):
        if dp.get(key) in (None, "null"):
            continue
        findings.append({
            "check": "decided_param_not_executed", "severity": "structural",
            "detail": (f"decided_params.{key}={dp[key]} is recorded but never executed: "
                       f"{why}. Either wire it through or drop it from the plan -- do not "
                       "report it as protocol and do not use it as a remedy.")})
    return findings


# NO_SOURCE_ROW is deliberately absent: it reports a gap in ff_provenance.py's own
# lookup, not a defect in the field, and must never block a plan or change a field choice
_PROVENANCE_BLOCKING = ("LOCAL_PATCH", "ZERO_SUBSTITUTED")


def _forcefield_findings(plan: dict) -> list:
    """D-01_ff must name a field that was measured admissible for THIS SMILES.

    Admissibility is the one clause in policies.forcefield.require that a plan can
    silently violate: the class default applies whether or not the field can represent
    the molecule, and the only previous symptom was the build crashing. select_forcefield.py
    records what it measured; this checks the plan agrees with it.
    """
    findings = []
    d = next((x for x in plan.get("decisions", []) if x.get("id") == "D-01_ff"), None)
    if not d:
        return findings
    choice = d.get("choice")
    admissible = d.get("admissible")
    dp_ff = plan.get("decided_params", {}).get("preferred_ff")

    if isinstance(admissible, list) and choice and choice not in admissible:
        findings.append({
            "check": "ff_not_admissible", "severity": "structural",
            "detail": (f"D-01_ff.choice={choice!r} is not in the measured admissible set "
                       f"{admissible} — the field cannot integrate or cannot type this "
                       "SMILES, so the build will fail or the parameters are not this "
                       "molecule's. Re-run orchestration/scripts/select_forcefield.py.")})
    if isinstance(admissible, list) and not admissible:
        findings.append({
            "check": "ff_no_admissible_field", "severity": "structural",
            "detail": ("no field was measured admissible for this SMILES — escalate to "
                       "human review rather than planning a run that cannot be built.")})
    if choice and dp_ff and dp_ff != choice:
        findings.append({
            "check": "ff_choice_not_applied", "severity": "structural",
            "detail": (f"decided_params.preferred_ff={dp_ff!r} disagrees with "
                       f"D-01_ff.choice={choice!r}. Hardware selection keys off "
                       "decided_params.preferred_ff, so the two must match.")})

    flags = d.get("provenance_flags") or {}
    blocking = sorted(f for f in flags if f in _PROVENANCE_BLOCKING and flags[f])
    acknowledged = any(u.get("name") == "ff_parameter_provenance"
                       for u in plan.get("uncertainties", []))
    if blocking and not acknowledged:
        findings.append({
            "check": "ff_provenance_unacknowledged", "severity": "structural",
            "detail": (f"D-01_ff.provenance_flags {blocking} record parameters that were "
                       "locally patched, silently zeroed, or unexplained, and no "
                       "uncertainties entry named 'ff_parameter_provenance' acknowledges "
                       "them. The flag does not veto the field — it must be carried as a "
                       "stated uncertainty, not inherited silently.")})
    return findings


def _system_size_findings(plan: dict) -> list:
    """D-04_system_size must not silently under-provision DP for a floor the class's own
    cited literature already documents (Fox-Flory for tg -- the only mechanized DP floor;
    entanglement DP@Me for bulk_modulus is advisory only, see select_system_size.py).

    Mirrors _hardware_findings: select_system_size.py is re-run live against the plan's
    own smiles/properties, same as _hardware_findings does with select_hardware.py. A
    floor violation does not block the plan outright, it must be raised or carried as a
    stated uncertainty -- same acknowledgeable-flag pattern as _forcefield_findings'
    provenance check.
    """
    findings = []
    dp_dict = plan.get("decided_params", {})
    smiles, polymer_class = plan.get("smiles"), plan.get("polymer_class")
    if not smiles or not polymer_class:
        return findings

    try:
        rec = select_system_size(polymer_class, smiles,
                                 properties=plan.get("properties"),
                                 dp_typical=dp_dict.get("dp_typical"),
                                 nchain=dp_dict.get("nchain"))
    except Exception as e:  # noqa: BLE001 -- a broken check must not block a plan
        findings.append({"check": "system_size_safety", "severity": "structural",
                         "detail": f"select_system_size.py raised: {e}"})
        return findings
    if "error" in rec:
        return findings

    required_floor = rec["decision"].get("required_dp_floor")
    if required_floor is None:
        return findings
    dp = dp_dict.get("dp_typical")
    if dp is None or dp >= required_floor:
        return findings
    acknowledged = any(u.get("name") == "system_size_dp_floor"
                       for u in plan.get("uncertainties", []))
    if not acknowledged:
        findings.append({
            "check": "system_size_dp_floor_unacknowledged", "severity": "structural",
            "detail": (f"decided_params.dp_typical={dp} is below the measured "
                      f"required_dp_floor={required_floor} ({rec['decision'].get('floor_sources')}) "
                      "and no uncertainties entry named 'system_size_dp_floor' acknowledges "
                      "it. Raise dp_typical to the floor or record the gap as a stated "
                      "uncertainty -- re-run orchestration/scripts/select_system_size.py.")})
    return findings


def _system_size_over_provisioned_findings(plan: dict) -> list:
    """Symmetric to _system_size_findings above, but for the OTHER direction: a
    reasoned/novel plan whose dp_typical clears select_system_size.py's own
    size_over_provisioned threshold (>1.5x the mechanized floor) without any
    acknowledgment in the plan.

    Gated on plan_mode=="reasoned" -- a protocol_validated replay must never be touched
    by this check (shrinking/flagging a frozen protocol is exactly what materialize_plan()
    is structurally prevented from doing; this check must not second-guess a replay either).

    Expected to basically never fire for a plan actually produced by
    scientific_control.py:materialize_plan(), which self-acknowledges this exact condition
    (an uncertainties[] entry named "system_size_over_provisioned") whenever it applies --
    auto-filled, literature-grounded, or from the agent's own override. This is defense in
    depth for a hand-edited plan or one produced by a path that skipped that step, matching
    this file's existing practice of re-deriving live rather than trusting the plan's own
    claims.

    Still live after the 2026-09-02 sizing change, though its reachable inputs narrowed: with
    class defaults gone, the auto-fill can never over-provision (the derived DP is the floor),
    so what remains is an explicit Planner dp_typical override or a hand-edited plan. Verified
    by execution before this note was written, not inferred -- an over-provisioned override
    does still reach both this check and materialize_plan()'s acknowledgment.
    """
    findings = []
    if plan.get("plan_mode") != "reasoned":
        return findings
    dp_dict = plan.get("decided_params", {})
    smiles, polymer_class = plan.get("smiles"), plan.get("polymer_class")
    dp = dp_dict.get("dp_typical")
    if not smiles or not polymer_class or dp is None:
        return findings

    try:
        rec = select_system_size(polymer_class, smiles, properties=plan.get("properties"),
                                 dp_typical=dp, nchain=dp_dict.get("nchain"))
    except Exception as e:  # noqa: BLE001 -- a broken check must not block a plan
        findings.append({"check": "system_size_safety", "severity": "structural",
                         "detail": f"select_system_size.py raised: {e}"})
        return findings
    if "error" in rec:
        return findings

    if not any(u.get("name") == "size_over_provisioned" for u in rec.get("uncertainties", [])):
        return findings
    acknowledged = any(u.get("name") == "system_size_over_provisioned"
                      for u in plan.get("uncertainties", []))
    if not acknowledged:
        findings.append({
            "check": "system_size_over_provisioned_unacknowledged", "severity": "structural",
            "detail": (f"decided_params.dp_typical={dp} clears select_system_size.py's "
                      "size_over_provisioned threshold and no uncertainties entry named "
                      "'system_size_over_provisioned' acknowledges it. A plan built through "
                      "materialize_plan() self-acknowledges this automatically -- re-run it, "
                      "or add the uncertainty by hand if this plan was edited directly.")})
    return findings


def validate_plan(plan: dict, policy: dict) -> list:
    findings = []
    findings += _criteria_and_evidence_findings(plan, policy)
    findings += _stage_schema_findings(plan, policy)
    findings += _stage_properties_findings(plan)
    findings += _uncertainty_findings(plan, policy)
    findings += _exp_tg_companion_findings(plan)
    findings += _tg_window_ceiling_findings(plan)
    findings += _hardware_findings(plan)
    findings += _forcefield_findings(plan)
    findings += _system_size_findings(plan)
    findings += _system_size_over_provisioned_findings(plan)
    findings += _finite_size_findings(plan)
    findings += _unimplemented_param_findings(plan)
    findings += _overridden_param_findings(plan)
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
