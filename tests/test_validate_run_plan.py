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
    replayed plan that dropped it.

    Asserts on the stages named, not on the prose: the check is a set comparison against
    track_registry now, so its wording is generic while its verdict is total.
    """
    for prop in ("density", "bulk_modulus", "shear_modulus"):
        findings = vrp._stage_properties_findings(_props_plan([prop], _ALWAYS))
        detail = " ".join(f["detail"] for f in findings
                          if f["check"] == "stage_properties")
        assert "cool" in detail and "cool-check" in detail, (prop, findings)


def test_the_cooling_stage_present_satisfies_it():
    assert vrp._stage_properties_findings(
        _props_plan(["density"], _ALWAYS + ["cool", "cool-check"])) == []


def test_every_requestable_property_is_covered_not_just_tg_and_bulk_modulus():
    """The clause-per-property version covered `tg` and `bulk_modulus` only, so a plan
    requesting shear_modulus with no `deform` stage passed, and melt_density had no clause at
    all. Asking the registry makes the check total by construction."""
    import track_registry
    for prop in sorted(track_registry.VALID_PROPERTIES):
        routed = track_registry.planned_stage_names({prop})
        assert vrp._stage_properties_findings(_props_plan([prop], routed)) == [], prop
        for dropped in routed:
            if dropped in ("build", "run-summary"):
                continue
            short = [st for st in routed if st != dropped]
            findings = vrp._stage_properties_findings(_props_plan([prop], short))
            assert findings, f"{prop} without {dropped} was accepted"


def test_a_stage_the_properties_do_not_route_is_a_defect():
    """The inverse defect the clause-per-property version could not express: a plan that names
    a stage nothing asked for describes a run the executor will not perform."""
    findings = vrp._stage_properties_findings(
        _props_plan(["melt_density"], _ALWAYS + ["murnaghan", "analyze-bm"]))
    detail = " ".join(f["detail"] for f in findings)
    assert "murnaghan" in detail and "do not route" in detail


def test_a_melt_only_or_tg_only_plan_needs_no_cooling_stage():
    """The point of the split: neither melt_density nor tg is measured at the assessment
    temperature, so neither pays for a descent."""
    assert vrp._stage_properties_findings(_props_plan(["melt_density"], _ALWAYS)) == []
    assert vrp._stage_properties_findings(
        _props_plan(["tg"], _ALWAYS + ["tg", "analyze-tg"])) == []


