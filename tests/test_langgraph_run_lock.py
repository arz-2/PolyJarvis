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
import time
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


def test_a_zombie_driver_does_not_wedge_the_run(tmp_path):
    """A lock whose PID is a ZOMBIE is stale. "Gone" has to mean gone, not merely unreaped.

    os.kill(pid, 0) succeeds on a zombie -- the process table entry survives until the parent
    reaps it -- so the liveness probe reported a dead driver as alive and RunLock refused the
    run as `locked`. Anything that spawns run_graph with Popen and never waits leaves zombies
    behind; the rev2 campaign's queue runner does exactly that. On 2026-09-12, killing the
    PEEK_2 and PSU_2 drivers to pick up a GPU fix left both runs refused `locked` by their own
    dead selves, with their equilibration chains still running on the GPUs.
    """
    pid = os.fork()
    if pid == 0:                       # child: exit at once, become a zombie
        os._exit(0)
    try:
        for _ in range(200):           # wait for the child to actually reach Z
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[-1].split(" ", 1)[0]
            if state == "Z":
                break
            time.sleep(0.01)
        assert state == "Z", f"child never became a zombie (state {state!r})"
        os.kill(pid, 0)                # the probe that used to be the whole test

        (tmp_path / "raw").mkdir(parents=True, exist_ok=True)
        (tmp_path / "raw" / ".graph.lock").write_text(
            json.dumps({"pid": pid, "started_at": "2026-09-12T00:00:00+00:00"}))

        assert RunLock(tmp_path)._stale() is True
        lock = RunLock(tmp_path)
        assert lock.acquire() is True
        lock.release()
    finally:
        os.waitpid(pid, 0)
