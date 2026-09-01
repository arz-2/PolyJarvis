"""Free measurements are reported, flagged, and never able to fail a run.

Asking for Tg already computes thermal expansion (glassy and rubbery), a transition width and a
density at every swept temperature -- extract_thermal writes all of it to thermal.json and none
of it reached the report. Surfacing them is the only new work; the physics already ran.

The contract, in one line: a byproduct annotates. It carries its own gate verdict so a doubtful
number cannot be quoted without its doubt, and it is structurally incapable of failing a run that
did not ask for it.
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"))

import track_registry as tr  # noqa: E402
from generate_run_summary import _collect_byproducts  # noqa: E402


def _spec(properties):
    return [{"name": o.name, "produced_by": o.produced_by, "track": o.track,
             "source_json": o.extractor_json, "field": o.extractor_field,
             "gate_field": o.gate_field, "unit": o.unit}
            for o in tr.byproducts_for(properties)]


def _write(tmp_path, properties):
    p = tmp_path / "byproducts_spec.json"
    p.write_text(json.dumps(_spec(properties)))
    return str(p)


THERMAL_OK = {
    "Tg_K": 532.7,
    "cte_glassy_per_K": 2.13e-4, "slope_signs_valid": True,
    "cte_rubbery_per_K": 3.87e-4, "slope_ordering_valid": True,
    "transition_width_c_K": 41.2, "fit_quality": "GOOD",
}


def test_a_tg_request_surfaces_its_free_measurements(tmp_path):
    got = _collect_byproducts(_write(tmp_path, {"tg"}), {"thermal.json": THERMAL_OK})
    assert set(got) == {"cte_glass", "cte_rubber", "tg_transition_width"}
    assert got["cte_glass"]["value"] == 2.13e-4
    assert got["cte_glass"]["unit"] == "1/K"
    assert got["cte_glass"]["produced_by"] == "tg"
    assert got["cte_glass"]["source"] == "thermal.json:cte_glassy_per_K"


def test_a_failing_byproduct_is_reported_with_its_verdict_attached(tmp_path):
    """The chosen contract: show the number AND the doubt, together. The verdict travels with
    the value so it cannot be quoted without it -- and `blocking: False` says in the artifact
    itself that this did not and could not affect the run's outcome."""
    thermal = {**THERMAL_OK, "slope_ordering_valid": False}
    got = _collect_byproducts(_write(tmp_path, {"tg"}), {"thermal.json": thermal})
    assert got["cte_rubber"]["value"] == 3.87e-4       # not hidden
    assert got["cte_rubber"]["gate"]["verdict"] is False
    assert got["cte_rubber"]["blocking"] is False


def test_every_byproduct_is_non_blocking_by_construction(tmp_path):
    got = _collect_byproducts(_write(tmp_path, {"tg", "bulk_modulus", "density"}),
                              {"thermal.json": THERMAL_OK})
    assert got and all(e["blocking"] is False for e in got.values())


def test_the_block_is_sparse_so_absent_is_distinguishable_from_rejected(tmp_path):
    """An entry appears only when its field actually resolved. Never null-filled: a reader must
    be able to tell 'measured and doubtful' from 'never measured'."""
    thermal = {k: v for k, v in THERMAL_OK.items() if k != "cte_rubbery_per_K"}
    got = _collect_byproducts(_write(tmp_path, {"tg"}), {"thermal.json": thermal})
    assert "cte_rubber" not in got
    assert "cte_glass" in got


def test_a_request_with_no_byproducts_writes_no_spec_and_yields_nothing(tmp_path):
    assert tr.byproducts_for({"density"}) == ()
    assert _collect_byproducts(None, {}) == {}


def test_an_unreadable_spec_never_breaks_the_summary(tmp_path):
    """Nothing about a free extra may take down the report of the thing that WAS requested."""
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert _collect_byproducts(str(bad), {"thermal.json": THERMAL_OK}) == {}
    assert _collect_byproducts(str(tmp_path / "missing.json"), {}) == {}


def test_byproducts_never_enter_the_binding_gate_vocabulary():
    """The structural guarantee behind 'never blocking': workflow_engine.binding_gate_failure
    keys off a fixed set of verdict fields per macro stage. A byproduct's gate field must not be
    among them, or a bad free measurement could fail a run nobody asked to measure it in."""
    import inspect
    import workflow_engine as we
    source = inspect.getsource(we.binding_gate_failure)
    for obs in tr.OBSERVABLES.values():
        if obs.kind == "byproduct" and obs.gate_field:
            assert obs.gate_field not in source, (
                f"{obs.name}'s gate field {obs.gate_field!r} is read by binding_gate_failure"
            )
