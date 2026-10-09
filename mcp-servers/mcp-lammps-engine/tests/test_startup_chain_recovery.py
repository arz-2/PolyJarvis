"""_recover_interrupted_chains() must settle legacy in-process chains without crashing startup.

It used to re-launch them on `_lammps_chain_background`, a name that was never defined, so a
run_state.json holding a running "lammps_chain" raised NameError before mcp.run(). Current
chains ("lammps_nohup_chain") run detached and must not be touched.

Requires the `mcp` package, same as this suite's other server.py-level tests.
"""
import pytest

pytest.importorskip("mcp")

from test_run_manager_persistence import _load_server_module  # noqa: E402


def _server_with_runs(tmp_path, monkeypatch, runs):
    mod = _load_server_module(tmp_path, monkeypatch)
    rm = mod.RunManager()
    rm.runs = runs
    monkeypatch.setattr(mod, "run_manager", rm)
    return mod, rm


def _chain(run_type, stages, status="running"):
    return {"run_id": "c1", "run_type": run_type, "status": status, "meta": {"stages": stages}}


def test_unfinished_legacy_chain_is_failed_not_relaunched(tmp_path, monkeypatch):
    stage = {"name": "npt", "work_dir": str(tmp_path), "output_data": str(tmp_path / "missing.data")}
    mod, rm = _server_with_runs(tmp_path, monkeypatch, {"c1": _chain("lammps_chain", [stage])})

    mod._recover_interrupted_chains()

    assert rm.runs["c1"]["status"] == "failed"
    assert "resubmit" in rm.runs["c1"]["error"]


def test_legacy_chain_with_every_output_on_disk_is_completed(tmp_path, monkeypatch):
    out = tmp_path / "npt_out.data"
    out.write_text("")
    stage = {"name": "npt", "work_dir": str(tmp_path), "output_data": str(out)}
    mod, rm = _server_with_runs(tmp_path, monkeypatch, {"c1": _chain("lammps_chain", [stage])})

    mod._recover_interrupted_chains()

    assert rm.runs["c1"]["status"] == "completed"


def test_detached_nohup_chain_is_left_alone(tmp_path, monkeypatch):
    stage = {"name": "npt", "work_dir": str(tmp_path), "output_data": str(tmp_path / "missing.data")}
    mod, rm = _server_with_runs(tmp_path, monkeypatch, {"c1": _chain("lammps_nohup_chain", [stage])})

    mod._recover_interrupted_chains()

    assert rm.runs["c1"]["status"] == "running"
