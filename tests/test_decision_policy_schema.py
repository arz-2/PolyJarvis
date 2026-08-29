"""Schema guard for orchestration/decision_policy.json.

decision_policy.json used to carry ~52KB of prose (rationale, evidence-level
definitions, the confidence-gate description) inline alongside the handful of
fields code actually reads. That prose now lives in docs/decision_rationale.md;
this file only holds what orchestration/scripts/*.py reads at runtime. This test
pins the paths those readers hard-index, so a future edit that drops one of them
fails loudly here instead of silently breaking scientific_control.py,
validate_run_plan.py, make_deterministic_plan.py, or remedy_economics.py.
"""
import json
from pathlib import Path

POLICY_PATH = Path(__file__).resolve().parents[1] / "orchestration" / "decision_policy.json"

# decision name -> per-decision keys read by scientific_control.planning_context()
# and make_deterministic_plan._policy_criteria()/validate_run_plan.py.
PER_DECISION_KEYS = {"decision_id", "evaluate", "evidence_required", "default_source"}

REMEDY_ECONOMICS_THRESHOLD_KEYS = {
    "variance_limited_sigma", "min_margin_factor", "converged_cost_ceiling_hours",
}


def load_policy():
    return json.loads(POLICY_PATH.read_text())


def test_top_level_code_read_keys_are_present():
    policy = load_policy()

    assert "stage_schema_requirements" in policy
    assert "uncertainty_reduction_probes" in policy
    assert "policies" in policy


def test_every_policy_entry_carries_the_fields_code_reads():
    policy = load_policy()

    for name, entry in policy["policies"].items():
        missing = PER_DECISION_KEYS - entry.keys()
        assert not missing, f"policies.{name} is missing {missing}"


def test_remedy_economics_thresholds_are_reachable_at_their_hardcoded_path():
    policy = load_policy()

    thresholds = policy["policies"]["equilibration"]["remedy_economics"]["thresholds"]
    missing = REMEDY_ECONOMICS_THRESHOLD_KEYS - thresholds.keys()
    assert not missing, f"remedy_economics.thresholds is missing {missing}"
    assert all(isinstance(v, (int, float)) for v in thresholds.values())


def test_uncertainty_reduction_probes_expose_at_least_one_real_probe():
    policy = load_policy()

    probe_names = set(policy["uncertainty_reduction_probes"].keys()) - {"description"}
    assert probe_names, "uncertainty_reduction_probes has no probes beyond 'description'"
