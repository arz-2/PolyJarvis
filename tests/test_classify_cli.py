"""classify_cli.classify_polymer/classify_batch — the subprocess-wrapping contract.

classify_cli shells into the mol-builder conda env for RadonPy, so these are pure-logic
tests of its wrapping behaviour with mol_python.run_in_mol_env monkeypatched -- the same
convention test_chem_similarity.py uses for protocol_evidence's RDKit seam. The real call
is exercised by tests/test_class_agreement.py under requires_binaries.

The behaviour that matters here is the refusal path. polymer_class drives charge_method,
electrostatics, cutoff_A, dt_fs, T_equil_K, density_initial_gcm3, the per-member
experimental bands and the tacticity default, so a wrapper that turned an unresolved class
into a plausible-looking guess would corrupt a whole campaign quietly. Every failure mode
below must raise, not return.
"""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import classify_cli  # noqa: E402


class _FakeCompleted:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def _patch(monkeypatch, *, stdout="", stderr="", returncode=0, capture=None):
    def fake(**kwargs):
        if capture is not None:
            capture.update(kwargs)
        return _FakeCompleted(stdout, stderr, returncode)
    monkeypatch.setattr(classify_cli, "run_in_mol_env", fake)


PSTR_PAYLOAD = {
    "smiles": "*CC(*)c1ccccc1", "class_id": 2, "polyinfo_class": "PSTR",
    "polymer_class": "PSTR", "class_source": "radonpy_polyinfo", "priority_rank": 16,
    "flags": {"PSTR": True, "PVNL": True}, "co_occurring": ["PVNL"], "runner_up": "PVNL",
    "groups": {"PSTR": {"location": "backbone"}},
}


def test_returns_the_full_profile_not_just_a_label(monkeypatch):
    _patch(monkeypatch, stdout=json.dumps(PSTR_PAYLOAD))
    result = classify_cli.classify_polymer("*CC(*)c1ccccc1")
    assert result["polymer_class"] == "PSTR"
    # The group profile is the point of this wrapper existing; a caller that only wanted a
    # label could have read polymer_rules.json.
    assert result["groups"]["PSTR"]["location"] == "backbone"
    assert result["co_occurring"] == ["PVNL"]


def test_reaches_radonpy_in_the_mol_builder_env_not_radonpy_env(monkeypatch):
    """RadonPy is a site-package in `mol-builder`; run_in_mol_env defaults to `radonpy`,
    which is the env every OTHER rdkit_cli wrapper wants. Getting this wrong fails at
    import time inside the subprocess, where the error is much harder to read."""
    seen = {}
    _patch(monkeypatch, stdout=json.dumps(PSTR_PAYLOAD), capture=seen)
    classify_cli.classify_polymer("*CC(*)c1ccccc1")
    assert seen["env"] == "mol-builder"
    assert seen["args"][:2] == ["classify", "--smiles"]
    # The SMILES travels as an argv element, never interpolated into shell text.
    assert seen["args"][2] == "*CC(*)c1ccccc1"


def test_unresolved_class_raises_rather_than_guessing(monkeypatch):
    _patch(monkeypatch, stdout=json.dumps({
        "smiles": "[Xe]", "error": "UNRESOLVED_CLASS",
        "detail": "polyinfo_classifier returned class_id=0", "class_id": 0}))
    with pytest.raises(classify_cli.ClassificationError, match="UNRESOLVED_CLASS"):
        classify_cli.classify_polymer("[Xe]")


def test_empty_output_raises_with_stderr_attached(monkeypatch):
    _patch(monkeypatch, stdout="", stderr="ModuleNotFoundError: radonpy", returncode=1)
    with pytest.raises(classify_cli.ClassificationError, match="radonpy"):
        classify_cli.classify_polymer("*CC*")


def test_non_json_output_raises_instead_of_propagating_a_decode_error(monkeypatch):
    _patch(monkeypatch, stdout="conda: command not found")
    with pytest.raises(classify_cli.ClassificationError, match="non-JSON"):
        classify_cli.classify_polymer("*CC*")


def test_timeout_raises_classification_error_not_the_raw_subprocess_error(monkeypatch):
    import subprocess

    def fake(**kwargs):
        raise subprocess.TimeoutExpired(cmd="python3", timeout=kwargs["timeout"])
    monkeypatch.setattr(classify_cli, "run_in_mol_env", fake)
    with pytest.raises(classify_cli.ClassificationError, match="timed out"):
        classify_cli.classify_polymer("*CC*")


def test_batch_crosses_the_conda_seam_exactly_once(monkeypatch):
    """A per-SMILES round trip is what makes a 1077-molecule sweep take hours instead of
    minutes -- the same reasoning rdkit_cli's match-moieties --input records."""
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        payload = json.loads(Path(kwargs["args"][2]).read_text())
        return _FakeCompleted(json.dumps(
            {"results": [{"smiles": s, "polymer_class": "PHYC"} for s in payload]}))
    monkeypatch.setattr(classify_cli, "run_in_mol_env", fake)

    results = classify_cli.classify_batch(["*CC*", "*CC(C)*", "*CCC*"])
    assert len(calls) == 1
    assert len(results) == 3
    assert calls[0]["args"][1] == "--input"


def test_batch_reports_per_smiles_errors_instead_of_raising(monkeypatch):
    """One unclassifiable molecule must not sink a whole sweep -- classify_batch's
    contract deliberately differs from classify_polymer's here."""
    _patch(monkeypatch, stdout=json.dumps({"results": [
        {"smiles": "*CC*", "polymer_class": "PHYC"},
        {"smiles": "bad", "error": "UNRESOLVED_CLASS"}]}))
    results = classify_cli.classify_batch(["*CC*", "bad"])
    assert results[0]["polymer_class"] == "PHYC"
    assert results[1]["error"] == "UNRESOLVED_CLASS"


def test_batch_of_nothing_does_not_shell_out_at_all(monkeypatch):
    def fake(**kwargs):
        raise AssertionError("should not have crossed the seam for an empty list")
    monkeypatch.setattr(classify_cli, "run_in_mol_env", fake)
    assert classify_cli.classify_batch([]) == []


def test_batch_uses_a_longer_timeout_than_a_single_call():
    """make_cyclicpolymer builds a real 4-mer per SMILES; run_in_mol_env's own 30 s default
    is sized for single-molecule RDKit calls and would kill any real sweep."""
    assert classify_cli.BATCH_TIMEOUT > classify_cli.DEFAULT_TIMEOUT > 30
