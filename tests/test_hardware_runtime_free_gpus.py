"""free_gpus must not count the desktop as contention.

On this workstation GPU 3 drives the display: Xorg + gnome-shell hold ~802 MiB, two above
IDLE_MEM_MB. It was the only card with no compute process on it, and the only card free_gpus()
would never return -- PLLA_3's first equilibration claim failed with `available: []` while GPU 3
sat at 0% utilisation and three other cards ran LAMMPS.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "orchestration" / "scripts"))
import hardware_runtime as hr


@pytest.fixture
def no_claims(monkeypatch):
    monkeypatch.setattr(hr, "claims", lambda: {})


def test_a_display_gpu_with_no_compute_process_is_free(monkeypatch, no_claims):
    monkeypatch.setattr(hr, "gpu_status", lambda: [
        {"index": 3, "util": 0, "mem_used_mb": 802, "uuid": "GPU-d", "compute_mem_mb": 0},
    ])
    assert hr.free_gpus() == [3], "graphics memory is not contention for a compute run"


def test_a_gpu_running_lammps_is_not_free(monkeypatch, no_claims):
    monkeypatch.setattr(hr, "gpu_status", lambda: [
        {"index": 0, "util": 88, "mem_used_mb": 291, "uuid": "GPU-a", "compute_mem_mb": 291},
        # idle-looking util but a resident compute process: still busy
        {"index": 1, "util": 0, "mem_used_mb": 9000, "uuid": "GPU-b", "compute_mem_mb": 9000},
    ])
    assert hr.free_gpus() == []


def test_when_the_compute_query_fails_it_falls_back_to_the_card_total(monkeypatch, no_claims):
    """Never call every card free because nvidia-smi's compute-apps query broke."""
    monkeypatch.setattr(hr, "_compute_mem_by_uuid", lambda: {})
    monkeypatch.setattr(hr.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "0, 0, 9000, GPU-a\n1, 0, 10, GPU-b\n"})())
    got = hr.gpu_status()
    assert got[0]["compute_mem_mb"] == 9000, "empty compute map must fall back to the total"
    assert got[1]["compute_mem_mb"] == 10
    monkeypatch.setattr(hr, "gpu_status", lambda: got)
    assert hr.free_gpus() == [1], "the 9000 MB card must stay excluded on the fallback path"
