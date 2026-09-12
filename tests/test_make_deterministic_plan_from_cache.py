"""make_deterministic_plan.py's fast path should build a plan from the SYSTEM (a validated
cache entry keyed by exact canonical SMILES), not just the polymer CLASS, whenever one exists
and covers the requested properties. This is the fix for the "plan is class-keyed, not
system-keyed" gap: previously --smiles was accepted but silently ignored.

rules_common.canonicalize shells into a conda env, so it's monkeypatched to identity here,
matching the pattern established in tests/test_select_system_size.py.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import rules_common
from make_deterministic_plan import (  # noqa: E402
    _try_cache, make_plan_from_cache, make_plan,
)
from rules_common import load_rules, get_class_entry  # noqa: E402

SMILES = "*CC*"
CLASS = "PHYC"
PROPERTIES = {"density", "tg"}


@pytest.fixture(autouse=True)
def _identity_canonicalize(monkeypatch):
    monkeypatch.setattr(rules_common, "canonicalize", lambda smi, *a, **k: smi)


def _write_cache(tmp_path, entry, smiles=SMILES):
    path = tmp_path / "cache.json"
    path.write_text(json.dumps({smiles: entry}))
    return path


def _validated_entry(**overrides):
    entry = {
        "protocol_validated": True,
        "validated_properties": ["density", "tg"],
        "polymer_class": CLASS,
        "source_run_name": "SRC1",
        "validated_at": "2026-08-20T00:00:00+00:00",
        "protocol": {
            "decided_params": {"preferred_ff": "trappe-ua", "cutoff_A": 14.0, "T_workflow_K": 300.0},
            "decisions": [{"id": "D-01_ff", "choice": "trappe-ua"}],
            "planned_stages": [{"stage": "build", "track": "foundation", "success_criteria": {}}],
        },
        "simulated_properties": {"tg": {"value_K": 220.6}},
        "notes": "test entry",
    }
    entry.update(overrides)
    return entry


def test_validated_entry_replays_frozen_protocol(tmp_path):
    cache_path = _write_cache(tmp_path, _validated_entry())
    plan = _try_cache("RUN1", CLASS, SMILES, PROPERTIES, cache_path)
    assert plan is not None
    assert plan["plan_mode"] == "deterministic"
    # charge_method/electrostatics are re-derived from the frozen field, so they appear
    # alongside the three frozen keys rather than being replayed.
    assert plan["decided_params"] == {"preferred_ff": "trappe-ua", "cutoff_A": 14.0,
                                      "T_workflow_K": 300.0,
                                      "charge_method": "embedded", "electrostatics": "lj_cut"}
    ids = [d["id"] for d in plan["decisions"]]
    assert ids == ["D-01_ff"]


def test_hardware_freshly_derived_not_frozen(tmp_path):
    """Hardware follows the frozen FIELD, never a frozen hardware row.

    It was a D-08_hardware decisions[] row appended on replay until 2026-09-04. Keeping it out
    of the frozen protocol is the point: engine/mpi/gpu are host-and-policy facts, so a run
    replayed on a recalibrated host must pick up the new policy rather than the old cell's."""
    cache_path = _write_cache(tmp_path, _validated_entry())
    plan = _try_cache("RUN1", CLASS, SMILES, PROPERTIES, cache_path)
    rules = load_rules()
    hp = rules["hardware_policy"]["by_forcefield"]["trappe"]
    assert plan["hardware"] == {"engine": hp["engine"], "mpi_ranks": hp["mpi"],
                                "gpu_per_run": hp["gpu_per_run"], "ff_family": "trappe"}
    assert not any(d["id"] == "D-08_hardware" for d in plan["decisions"])


def test_no_cache_file_falls_back_to_none(tmp_path):
    assert _try_cache("RUN1", CLASS, SMILES, PROPERTIES, tmp_path / "missing.json") is None


def test_no_matching_entry_falls_back_to_none(tmp_path):
    cache_path = _write_cache(tmp_path, _validated_entry(), smiles="*CC(C)C*")
    assert _try_cache("RUN1", CLASS, SMILES, PROPERTIES, cache_path) is None


def test_protocol_not_validated_falls_back_to_none(tmp_path):
    cache_path = _write_cache(tmp_path, _validated_entry(protocol_validated=False))
    assert _try_cache("RUN1", CLASS, SMILES, PROPERTIES, cache_path) is None


def test_insufficient_validated_properties_falls_back_to_none(tmp_path):
    cache_path = _write_cache(tmp_path, _validated_entry(validated_properties=["density"]))
    assert _try_cache("RUN1", CLASS, SMILES, PROPERTIES, cache_path) is None


def test_polymer_class_mismatch_falls_back_to_none(tmp_path):
    cache_path = _write_cache(tmp_path, _validated_entry(polymer_class="PSTR"))
    assert _try_cache("RUN1", CLASS, SMILES, PROPERTIES, cache_path) is None


def test_no_smiles_falls_back_to_none(tmp_path):
    cache_path = _write_cache(tmp_path, _validated_entry())
    assert _try_cache("RUN1", CLASS, None, PROPERTIES, cache_path) is None


def test_make_plan_unchanged_when_try_cache_misses(tmp_path):
    """Regression guard: today's class-default make_plan() output is untouched by this feature
    when there's nothing to replay."""
    assert _try_cache("RUN1", CLASS, SMILES, PROPERTIES, tmp_path / "missing.json") is None
    plan = make_plan("RUN1", CLASS, SMILES, PROPERTIES)
    assert plan["plan_mode"] == "scaffold"
    assert plan["polymer_class"] == CLASS


def test_freeze_keys_carry_the_force_field_itself():
    """The field D-01 resolved must be frozen, not re-derived from the class table.

    write_characterization_cache.FREEZE_KEYS omitted preferred_ff until 2026-09-12, because
    SNAPSHOT_KEYS describes an unmodified class scaffold and D-01 RESOLVES the field rather
    than copying it. The consequence was silent and serious: a frozen protocol carried
    preferred_ff=None, so every replicate fell back to the class ff_accuracy_prior for the
    single most important decision in the plan -- invisible while the adjudicated field equals
    the prior, and a silent reversal the moment the D-01 probe cascade moves it off.
    """
    import write_characterization_cache as wcc
    assert "preferred_ff" in wcc.FREEZE_KEYS


def test_a_freeze_without_a_force_field_is_a_miss_not_a_wrong_replay(tmp_path):
    """A pre-2026-09-12 freeze must degrade to re-planning, never to a derived-from-nothing field.

    Replaying one resolved the empty force-field family, which handed the plan
    charge_method="RESP" -- a QM charge model -- while the replayed D-01 row still read the real
    field. The plan was internally inconsistent, and it would have built three PCFF systems with
    the wrong charge scheme. A cache MISS sends the run back to make_plan(), which is honest.
    """
    entry = _validated_entry()
    entry["protocol"]["decided_params"] = {k: v for k, v in
                                           entry["protocol"]["decided_params"].items()
                                           if k != "preferred_ff"}
    cache_path = _write_cache(tmp_path, entry)
    assert _try_cache("RUN_STALE", CLASS, SMILES, PROPERTIES, cache_path) is None


def test_replayed_charge_method_follows_the_frozen_field(tmp_path):
    """Everything the field implies is re-derived FROM THE FROZEN FIELD, so the two can never
    disagree -- the property make_plan_from_cache claims and, before preferred_ff was frozen,
    did not have."""
    entry = _validated_entry()
    entry["protocol"]["decided_params"]["preferred_ff"] = "pcff"
    entry["protocol"]["decisions"] = [{"id": "D-01_ff", "choice": "pcff"}]
    cache_path = _write_cache(tmp_path, entry)
    plan = _try_cache("RUN_PCFF", CLASS, SMILES, PROPERTIES, cache_path)
    assert plan is not None
    dp = plan["decided_params"]
    assert dp["preferred_ff"] == "pcff"
    assert dp["charge_method"] == "bond-increment"
    assert dp["electrostatics"] == "pppm"
    assert [d["choice"] for d in plan["decisions"]] == ["pcff"]


def test_a_replayed_plan_prices_itself(tmp_path):
    """materialize is skipped on a cache hit (it would overwrite the replayed protocol), and
    materialize is what normally writes cost_estimate -- so without this the plan reaches
    cost_guard_post with no total and is refused `cost_unknown`, making every replicate of every
    validated system unrunnable under a --max-gpu-hours ceiling."""
    entry = _validated_entry()
    # A real freeze always carries the cell (dp_typical/nchain are in SNAPSHOT_KEYS); the
    # minimal fixture above does not, and plan_cost_estimate correctly refuses to price a
    # plan with no cell rather than inventing one.
    entry["protocol"]["decided_params"].update({"dp_typical": 100, "nchain": 10})
    cache_path = _write_cache(tmp_path, entry)
    plan = _try_cache("RUN_PRICED", CLASS, SMILES, PROPERTIES, cache_path)
    assert plan is not None
    ce = plan["cost_estimate"]
    assert "error" not in ce, ce
    # A real priced block, not an error stub. total_gpu_hours is deliberately NOT asserted:
    # this fixture carries no stage-length knobs, so nothing is priceable and an honest
    # estimator returns no total. What regressed was cost_estimate being absent ENTIRELY,
    # which is what cost_guard_post refused on. The end-to-end total is exercised by the real
    # frozen protocols (PEEK replays at 5.777 GPU-h, identical to its source run).
    assert "stages" in ce and "unpriced_stages" in ce
