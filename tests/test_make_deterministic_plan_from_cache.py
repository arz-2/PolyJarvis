"""make_deterministic_plan.py's fast path should build a plan from the SYSTEM (a validated
cache entry keyed by exact canonical SMILES), not just the polymer CLASS, whenever one exists
and covers the requested properties. This is the fix for the "plan is class-keyed, not
system-keyed" gap: previously --smiles was accepted but silently ignored.

canon_smiles.canonicalize shells into a conda env, so it's monkeypatched to identity here,
matching the pattern established in tests/test_select_system_size.py.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import canon_smiles  # noqa: E402
from make_deterministic_plan import (  # noqa: E402
    _try_cache, make_plan_from_cache, make_plan, _build_hardware_decision, _policy_criteria,
)
from hw_common import load_rules, get_class_entry  # noqa: E402

SMILES = "*CC*"
CLASS = "PHYC"
PROPERTIES = {"density", "tg"}


@pytest.fixture(autouse=True)
def _identity_canonicalize(monkeypatch):
    monkeypatch.setattr(canon_smiles, "canonicalize", lambda smi, *a, **k: smi)


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
    assert plan["decided_params"] == {"preferred_ff": "trappe-ua", "cutoff_A": 14.0,
                                      "T_workflow_K": 300.0}
    ids = [d["id"] for d in plan["decisions"]]
    assert ids == ["D-01_ff", "D-08_hardware"]


def test_d08_hardware_freshly_resolved_not_frozen(tmp_path):
    cache_path = _write_cache(tmp_path, _validated_entry())
    plan = _try_cache("RUN1", CLASS, SMILES, PROPERTIES, cache_path)
    rules = load_rules()
    cls = get_class_entry(rules, CLASS)
    expected = _build_hardware_decision(cls, _policy_criteria().get("D-08_hardware", []))
    hardware_row = next(d for d in plan["decisions"] if d["id"] == "D-08_hardware")
    assert hardware_row == expected


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
