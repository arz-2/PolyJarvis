"""RunManager._save()/_load() must survive a mid-write crash without corrupting or silently
discarding run history.

_save() used to `open(STATE_FILE, "w")` and stream json.dump directly into it -- a process
killed or crashed mid-write left a truncated, syntactically invalid file on disk. Several
short-lived diagnostic processes importing this module alongside a live, long-running
orchestrator (all pointed at the one shared, cross-checkout run_state.json) each hold their own
in-memory `runs` snapshot and can race to save around the same moment, turning an ordinary race
into disk corruption. Hit live 2026-08-17: corrupted the real run_state.json mid-write.

Compounding it, _load()'s except-block reset straight to `self.runs = {}` with no trace of the
unreadable file -- the very next _save() from that reset state would have permanently overwritten
the corrupted-but-partially-recoverable file (63 of ~330+ run records were recoverable by hand).

Requires the `mcp` package (server.py imports fastmcp at module scope); skips cleanly when it
isn't installed, same as this suite's other server.py-level tests.
"""
import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

ENGINE_ROOT = Path(__file__).resolve().parent.parent


def _load_server_module(tmp_path, monkeypatch):
    """Import server.py fresh with STATE_FILE redirected into tmp_path, isolated from the
    real (shared, cross-checkout) run_state.json."""
    monkeypatch.setenv("LAMBDA_USER", "test")
    monkeypatch.setenv("LAMBDA_WORKDIR", str(tmp_path))
    monkeypatch.setenv("LAMBDA_LAMMPS", "/bin/true")
    old_cwd = os.getcwd()
    os.chdir(ENGINE_ROOT)
    if str(ENGINE_ROOT) not in sys.path:
        sys.path.insert(0, str(ENGINE_ROOT))
    spec = importlib.util.spec_from_file_location("lammps_engine_server_test", ENGINE_ROOT / "server.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    os.chdir(old_cwd)
    mod.STATE_FILE = tmp_path / "run_state.json"
    return mod


def test_save_is_atomic_no_temp_file_left_behind(tmp_path, monkeypatch):
    mod = _load_server_module(tmp_path, monkeypatch)
    rm = mod.RunManager()
    rm.runs = {"abc123": {"run_type": "test", "status": "completed"}}
    rm._save()

    assert mod.STATE_FILE.exists()
    assert json.loads(mod.STATE_FILE.read_text()) == rm.runs
    leftover_temp_files = list(tmp_path.glob(".run_state.json.*.tmp"))
    assert leftover_temp_files == [], f"temp file(s) left behind: {leftover_temp_files}"


def test_save_never_leaves_a_truncated_file_visible(tmp_path, monkeypatch):
    """A save that fails partway through must never leave a half-written file at STATE_FILE --
    os.replace only swaps in a fully-written temp file."""
    mod = _load_server_module(tmp_path, monkeypatch)
    rm = mod.RunManager()
    rm.runs = {"good": {"run_type": "test", "status": "completed"}}
    rm._save()
    original_bytes = mod.STATE_FILE.read_bytes()

    class Unserializable:
        def __repr__(self):
            raise RuntimeError("boom mid-write")

    rm.runs = {"good": {"status": "completed"}, "bad": Unserializable()}
    rm._save()  # swallows the error internally (existing behavior), must not corrupt the file

    assert mod.STATE_FILE.read_bytes() == original_bytes


def test_load_quarantines_corrupt_file_instead_of_discarding_it(tmp_path, monkeypatch):
    mod = _load_server_module(tmp_path, monkeypatch)
    mod.STATE_FILE.write_text('{"abc123": {"status": "completed"')  # truncated, invalid JSON

    rm = mod.RunManager()

    assert rm.runs == {}
    assert not mod.STATE_FILE.exists(), "corrupt file should be moved aside, not left in place"
    quarantined = list(tmp_path.glob("run_state.json.corrupt.*"))
    assert len(quarantined) == 1
    assert '"abc123"' in quarantined[0].read_text()


def test_load_of_valid_file_is_unaffected(tmp_path, monkeypatch):
    mod = _load_server_module(tmp_path, monkeypatch)
    mod.STATE_FILE.write_text(json.dumps({"abc123": {
        "run_type": "test", "status": "completed", "submitted_at": "x", "completed_at": "y",
    }}))

    rm = mod.RunManager()

    assert "abc123" in rm.runs
    assert mod.STATE_FILE.exists()
