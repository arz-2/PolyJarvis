"""pe.py — compute_similarities() shells into a conda env for RDKit, so
these are pure-logic tests of its subprocess-wrapping contract via monkeypatching
subprocess.run (same convention as canon_smiles.canonicalize's tests), plus one real
@requires_binaries smoke test of the actual RDKit call for a configured host."""
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import protocol_evidence as pe  # noqa: E402


class _FakeCompletedProcess:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


def test_compute_similarities_returns_parsed_scores(monkeypatch):
    payload = {"scores": {"*CC(*)(C)C(=O)OC": 1.0, "*CC(*)C(=O)OC": 0.62}, "errors": []}

    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(stdout=json.dumps(payload) + "\n")

    monkeypatch.setattr(pe.subprocess, "run", fake_run)
    result = pe.compute_similarities("*CC(*)(C)C(=O)OC", ["*CC(*)(C)C(=O)OC", "*CC(*)C(=O)OC"])
    assert result == payload


def test_compute_similarities_raises_on_nonzero_exit(monkeypatch):
    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(stdout="", stderr="rdkit not found", returncode=1)

    monkeypatch.setattr(pe.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="rdkit not found"):
        pe.compute_similarities("*CC*", ["*CC*"])


def test_compute_similarities_raises_on_empty_output(monkeypatch):
    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(stdout="", returncode=0)

    monkeypatch.setattr(pe.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError):
        pe.compute_similarities("*CC*", ["*CC*"])


def test_compute_similarities_cleans_up_temp_files(monkeypatch, tmp_path):
    created_paths = []
    real_named_temp = pe.tempfile.NamedTemporaryFile

    def tracking_named_temp(*args, **kwargs):
        f = real_named_temp(*args, **kwargs)
        created_paths.append(f.name)
        return f

    monkeypatch.setattr(pe.tempfile, "NamedTemporaryFile", tracking_named_temp)

    def fake_run(cmd, **kwargs):
        return _FakeCompletedProcess(stdout=json.dumps({"scores": {}, "errors": []}) + "\n")

    monkeypatch.setattr(pe.subprocess, "run", fake_run)
    pe.compute_similarities("*CC*", ["*CC*"])

    # Exactly one temp file: the candidate-list JSON. There were two until the RDKit code
    # moved into rdkit_cli.py -- run_in_mol_env(script=...) had to spill the fingerprint
    # snippet to a second temp .py on every call, which passing script_path=RDKIT_CLI
    # removes. Both then and now, nothing may survive the call.
    assert len(created_paths) == 1
    for p in created_paths:
        assert not Path(p).exists()


@pytest.mark.requires_binaries
def test_compute_similarities_real_rdkit_identical_smiles_scores_one():
    result = pe.compute_similarities("*CC(*)(C)C(=O)OC", ["*CC(*)(C)C(=O)OC", "*CC*"])
    assert result["scores"]["*CC(*)(C)C(=O)OC"] == pytest.approx(1.0)
    assert 0.0 <= result["scores"]["*CC*"] < 1.0
