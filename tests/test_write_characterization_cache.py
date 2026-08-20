"""write_characterization_cache.py freezes a completed campaign's actually-executed protocol
into guides/system_characterization_cache.json, keyed by canonical SMILES. These tests never
touch the real cache file -- every case passes an explicit cache_path under tmp_path.

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
import write_characterization_cache as wcc  # noqa: E402


@pytest.fixture(autouse=True)
def _identity_canonicalize(monkeypatch):
    monkeypatch.setattr(canon_smiles, "canonicalize", lambda smi, *a, **k: smi)


def _write(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj))


def _make_run(tmp_path, run_name="RUN1", *, properties=("density", "tg", "bulk_modulus"),
              stage_status=None, effective_parameters=None, remedy_history=None,
              accepted_attempt="attempt-0001", write_summary=True, smiles="*CC*"):
    run_dir = tmp_path / "data" / run_name
    plan = {
        "smiles": smiles,
        "polymer_class": "PHYC",
        "properties": list(properties),
        "decisions": [
            {"id": "D-01_ff", "choice": "trappe-ua"},
            {"id": "D-08_hardware", "choice": {"engine": "kokkos", "mpi_ranks": 1}},
        ],
        "planned_stages": [{"stage": "build", "track": "foundation", "success_criteria": {}}],
    }
    _write(run_dir / "raw" / "run_plan.json", plan)

    default_status = {"equilibration": "accepted", "thermal": "accepted",
                      "mechanical": "accepted", "summary": "accepted"}
    if stage_status:
        default_status.update(stage_status)
    stages = {name: {"status": status} for name, status in default_status.items()}
    stages["summary"]["accepted_attempt"] = accepted_attempt

    workflow_state = {
        "stages": stages,
        "effective_parameters": effective_parameters if effective_parameters is not None else {
            "preferred_ff": "trappe-ua", "cutoff_A": 14.0, "dt_fs": 1.0, "T_workflow_K": 300.0,
        },
    }
    if remedy_history is not None:
        workflow_state["remedy_history"] = remedy_history
    _write(run_dir / "workflow_state.json", workflow_state)

    if write_summary:
        results = {"tg": {"value_K": 220.6}, "density": {"value_g_cm3": 0.86},
                  "bulk_modulus": {"value_GPa": 1.85}}
        _write(run_dir / "attempts" / "summary" / accepted_attempt / "raw" / "run_summary.json",
              {"results": results})
    return run_dir, plan, workflow_state


def test_full_stage_acceptance_validates_all_requested_properties(tmp_path):
    _make_run(tmp_path, "RUN1")
    cache_path = tmp_path / "cache.json"
    entry = wcc.write_characterization_cache("RUN1", repo_root=tmp_path, cache_path=cache_path)
    assert entry is not None
    assert entry["protocol_validated"] is True
    assert entry["validated_properties"] == ["bulk_modulus", "density", "tg"]
    assert entry["simulated_properties"]["tg"]["value_K"] == 220.6
    on_disk = json.loads(cache_path.read_text())
    assert on_disk["*CC*"] == entry


def test_partial_stage_acceptance_excludes_unaccepted_property(tmp_path):
    _make_run(tmp_path, "RUN2", stage_status={"thermal": "remedy_required"})
    cache_path = tmp_path / "cache.json"
    entry = wcc.write_characterization_cache("RUN2", repo_root=tmp_path, cache_path=cache_path)
    assert entry["protocol_validated"] is True
    assert entry["validated_properties"] == ["bulk_modulus", "density"]
    assert "tg" not in entry["validated_properties"]


def test_freezes_effective_parameters_not_plan_decided_params(tmp_path):
    """The plan's own decided_params never even appears in run_plan.json here (this fixture
    omits it) -- the frozen protocol must come from workflow_state.effective_parameters, which
    is decided_params AS AMENDED by any mid-run remedy, not the plan's stale original."""
    remedy_history = [{"remedy_id": "melt_hold_extend", "application": 1,
                       "finding": {"stage": "equilibration"}}]
    _make_run(tmp_path, "RUN3",
             effective_parameters={"eq_annealing_cycles": 4, "T_workflow_K": 300.0},
             remedy_history=remedy_history)
    cache_path = tmp_path / "cache.json"
    entry = wcc.write_characterization_cache("RUN3", repo_root=tmp_path, cache_path=cache_path)
    assert entry["protocol"]["decided_params"]["eq_annealing_cycles"] == 4
    assert "melt_hold_extend" in entry["notes"]
    assert "equilibration" in entry["notes"]


def test_t_workflow_k_is_frozen_despite_not_being_in_snapshot_keys(tmp_path):
    from make_deterministic_plan import SNAPSHOT_KEYS
    assert "T_workflow_K" not in SNAPSHOT_KEYS
    _make_run(tmp_path, "RUN4", effective_parameters={"T_workflow_K": 450.0})
    cache_path = tmp_path / "cache.json"
    entry = wcc.write_characterization_cache("RUN4", repo_root=tmp_path, cache_path=cache_path)
    assert entry["protocol"]["decided_params"]["T_workflow_K"] == 450.0


def test_d08_hardware_decision_excluded_from_frozen_decisions(tmp_path):
    _make_run(tmp_path, "RUN5")
    cache_path = tmp_path / "cache.json"
    entry = wcc.write_characterization_cache("RUN5", repo_root=tmp_path, cache_path=cache_path)
    ids = [d["id"] for d in entry["protocol"]["decisions"]]
    assert "D-08_hardware" not in ids
    assert "D-01_ff" in ids


def test_merge_preserves_unrelated_legacy_fields(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({
        "*CC*": {"probe_tau_relax_reliable": True, "note": "hand-written legacy note"},
    }))
    _make_run(tmp_path, "RUN6")
    entry = wcc.write_characterization_cache("RUN6", repo_root=tmp_path, cache_path=cache_path)
    assert entry["probe_tau_relax_reliable"] is True
    assert entry["note"] == "hand-written legacy note"
    assert entry["protocol_validated"] is True


def test_requires_guard_blocks_protocol_validated(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({
        "*CC*": {"requires_cis_lock": True, "note": "EMC ignores SMILES stereo for this SMILES"},
    }))
    _make_run(tmp_path, "RUN7")
    entry = wcc.write_characterization_cache("RUN7", repo_root=tmp_path, cache_path=cache_path)
    assert entry["protocol_validated"] is False
    assert "requires_cis_lock" in entry["notes"]
    assert "protocol" not in entry  # never freeze a protocol block behind a live guard


def test_missing_smiles_writes_nothing(tmp_path):
    _make_run(tmp_path, "RUN8", smiles=None)
    cache_path = tmp_path / "cache.json"
    entry = wcc.write_characterization_cache("RUN8", repo_root=tmp_path, cache_path=cache_path)
    assert entry is None
    assert not cache_path.exists()


def test_canonicalization_failure_writes_nothing(tmp_path, monkeypatch):
    def _boom(smi, *a, **k):
        raise RuntimeError("RDKit could not parse SMILES")
    monkeypatch.setattr(canon_smiles, "canonicalize", _boom)
    _make_run(tmp_path, "RUN9")
    cache_path = tmp_path / "cache.json"
    entry = wcc.write_characterization_cache("RUN9", repo_root=tmp_path, cache_path=cache_path)
    assert entry is None
    assert not cache_path.exists()


def test_missing_run_plan_writes_nothing(tmp_path):
    cache_path = tmp_path / "cache.json"
    entry = wcc.write_characterization_cache("NEVER_RAN", repo_root=tmp_path, cache_path=cache_path)
    assert entry is None
