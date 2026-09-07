"""RunLock — one driver per run, and never a permanently wedged run.

make_deterministic_plan refuses to clobber an existing plan, but materialize rewrites
run_plan.json in place, so two drivers on one run_name interleave writes to it.
control_state.json is a session marker, not a lock, and cannot serve.

The failure mode on the other side matters just as much: a lock that outlives its holder
would wedge a run forever, and this driver is meant to run unattended. So a lock whose PID
is gone is stale and reclaimed.
"""
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "langgraph"))

from run_graph import RunLock  # noqa: E402


def test_acquire_creates_the_lock_and_records_the_holder(tmp_path):
    lock = RunLock(tmp_path)
    assert lock.acquire()
    payload = json.loads(lock.path.read_text())
    assert payload["pid"] == os.getpid()
    assert payload["started_at"]


def test_a_second_driver_cannot_acquire_a_live_lock(tmp_path):
    first = RunLock(tmp_path)
    assert first.acquire()
    assert RunLock(tmp_path).acquire() is False


def test_release_frees_it_for_the_next_driver(tmp_path):
    first = RunLock(tmp_path)
    first.acquire()
    first.release()
    assert not first.path.exists()
    assert RunLock(tmp_path).acquire()


def test_a_lock_left_by_a_dead_process_is_reclaimed(tmp_path):
    """A killed driver must not wedge the run -- the whole point of this being unattended."""
    lock = RunLock(tmp_path)
    lock.path.parent.mkdir(parents=True, exist_ok=True)
    # PID 0 is never a real user process, so os.kill(0, 0) raises and the lock reads stale.
    lock.path.write_text(json.dumps({"pid": 2 ** 31 - 1, "started_at": "2020-01-01T00:00:00Z"}))
    assert lock.acquire()
    assert json.loads(lock.path.read_text())["pid"] == os.getpid()


@pytest.mark.parametrize("content", ["{not json", "{}", '{"pid": "not-an-int"}', ""])
def test_an_unreadable_lock_is_treated_as_stale(tmp_path, content):
    """Better to reclaim a corrupt lock than to block a run on an unparseable file."""
    lock = RunLock(tmp_path)
    lock.path.parent.mkdir(parents=True, exist_ok=True)
    lock.path.write_text(content)
    assert lock.acquire()


def test_the_context_manager_always_releases(tmp_path):
    with RunLock(tmp_path) as lock:
        lock.acquire()
        path = lock.path
        assert path.exists()
    assert not path.exists()


def test_releasing_a_lock_it_does_not_hold_is_a_no_op(tmp_path):
    """A driver that failed to acquire must not delete the holder's lock on the way out."""
    holder = RunLock(tmp_path)
    holder.acquire()
    loser = RunLock(tmp_path)
    assert loser.acquire() is False
    loser.release()
    assert holder.path.exists(), "the loser deleted the winner's lock"


def test_the_lock_lives_under_the_run_directory_not_a_shared_path(tmp_path):
    """Locks are per-run: two different runs must never contend."""
    a, b = RunLock(tmp_path / "runA"), RunLock(tmp_path / "runB")
    assert a.acquire() and b.acquire()
    assert a.path != b.path
