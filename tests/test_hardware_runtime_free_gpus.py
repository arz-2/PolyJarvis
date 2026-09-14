"""free_gpus gates on whether the card is IDLE and whether our run FITS, not on used memory.

Two incidents shaped this. On 2026-09-11 a neighbour's training job grew its per-card allocation
from 754 MB to 5.8 GB on 40 GB A800s; every card crossed an absolute used-memory cap at once and
PE_1 could not reclaim a GPU on a box that was 85% idle by memory. And on the other workstation
GPU 3 drives the display (Xorg + gnome-shell ~802 MiB), which a used-memory cap likewise refused
while it sat at 0% utilisation (PLLA_3). Both are idle cards with room, and both must be free.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "orchestration" / "scripts"))
import hardware_runtime as hr

A800_MB = 40960


def card(index, util, used, total=A800_MB):
    return {"index": index, "util": util, "mem_used_mb": used, "mem_total_mb": total,
            "mem_free_mb": max(0, total - used)}


@pytest.fixture
def no_claims(monkeypatch):
    monkeypatch.setattr(hr, "claims", lambda: {})


def test_an_idle_card_with_a_neighbours_parked_context_is_free(monkeypatch, no_claims):
    monkeypatch.setattr(hr, "gpu_status", lambda: [card(0, util=0, used=5800)])
    assert hr.free_gpus() == [0], "5.8 GB parked on a 40 GB card leaves room for a run"


def test_a_display_gpu_with_room_is_free(monkeypatch, no_claims):
    monkeypatch.setattr(hr, "gpu_status", lambda: [card(3, util=0, used=802)])
    assert hr.free_gpus() == [3], "graphics memory is not contention for a compute run"


def test_a_busy_card_is_not_free_however_much_room_it_has(monkeypatch, no_claims):
    monkeypatch.setattr(hr, "gpu_status", lambda: [card(1, util=88, used=459)])
    assert hr.free_gpus() == []


def test_an_idle_card_without_room_is_not_free(monkeypatch, no_claims):
    used = A800_MB - hr.MIN_FREE_MEM_MB + 1
    monkeypatch.setattr(hr, "gpu_status", lambda: [card(2, util=0, used=used)])
    assert hr.free_gpus() == []


def test_a_claimed_card_is_not_free(monkeypatch):
    monkeypatch.setattr(hr, "claims", lambda: {0: {"run": "PE_2"}})
    monkeypatch.setattr(hr, "gpu_status", lambda: [card(0, util=0, used=10), card(1, util=0, used=10)])
    assert hr.free_gpus() == [1]


def test_gpu_status_derives_free_memory_from_the_card_total(monkeypatch):
    monkeypatch.setattr(hr.subprocess, "run", lambda *a, **k: type(
        "R", (), {"stdout": "0, 0, 9000, 40960\n1, 3, 10, 40960\n"})())
    got = hr.gpu_status()
    assert [(g["index"], g["mem_free_mb"]) for g in got] == [(0, 31960), (1, 40950)]
