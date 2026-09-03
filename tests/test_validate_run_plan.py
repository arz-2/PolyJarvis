"""validate_run_plan checks that are not hardware-related.

(_hardware_findings has its own file, tests/test_validate_run_plan_hardware.py.)
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import validate_run_plan as vrp  # noqa: E402


# ─── the cooling stage is required by anything measured at final_T_K ──────────────
#
# (The explicit-tg-window-vs-ceiling advisory that used to live here is gone with
# tg_t_high_K itself. It existed because that key hashed to the thermal stage while feeding
# the anneal ceiling; the sweep's top is T_melt_hold_K now, which is equilibration-hashed,
# so the mismatch it warned about cannot arise.)


def _props_plan(properties, stages):
    return {"properties": list(properties),
            "planned_stages": [{"stage": st, "track": "x", "success_criteria": {}}
                               for st in stages]}


_ALWAYS = ["build", "equil", "equil-check", "run-summary"]


def test_a_property_measured_at_final_T_requires_the_cooling_stage():
    """density and every modulus are measured on npt_final, which only the cooling stage
    produces. track_registry routes it in automatically; this catches a hand-written or
    replayed plan that dropped it."""
    for prop in ("density", "bulk_modulus", "shear_modulus"):
        findings = vrp._stage_properties_findings(_props_plan([prop], _ALWAYS))
        assert any(f["check"] == "stage_properties" and "final_T_K" in f["detail"]
                   for f in findings), prop


def test_the_cooling_stage_present_satisfies_it():
    findings = vrp._stage_properties_findings(
        _props_plan(["density"], _ALWAYS + ["cool", "cool-check"]))
    assert [f for f in findings if "final_T_K" in f["detail"]] == []


def test_a_melt_only_or_tg_only_plan_needs_no_cooling_stage():
    """The point of the split: neither melt_density nor tg is measured at the assessment
    temperature, so neither pays for a descent."""
    assert vrp._stage_properties_findings(_props_plan(["melt_density"], _ALWAYS)) == []
    assert vrp._stage_properties_findings(
        _props_plan(["tg"], _ALWAYS + ["tg", "analyze-tg"])) == []


