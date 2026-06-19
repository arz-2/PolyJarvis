"""Tests for the run-completion monitor command and chain sentinel/pidfile.

build_watch_command + pidfile_path live in monitor_utils (stdlib-only) so these
run in the base test env without fastmcp. The chain-script tests import server.py
and are skipped where the `mcp` dependency is unavailable (e.g. the base env).
"""
import subprocess

import pytest

from monitor_utils import build_watch_command, pidfile_path


SENTINEL = "/tmp/polyjarvis/sentinels/done_run123.json"
SDIR = "/tmp/polyjarvis/sentinels"


def test_pidfile_path_format():
    assert pidfile_path("run123", SDIR) == "/tmp/polyjarvis/sentinels/pid_run123"


def test_command_waits_on_sentinel_first_and_signals_complete():
    cmd = build_watch_command(SENTINEL, pidfile_path("run123", SDIR))
    assert SENTINEL in cmd
    assert "RUN_COMPLETE" in cmd
    assert 'while [ ! -f "$SENTINEL" ]' in cmd  # sentinel checked first each iteration


def test_command_reads_pidfile_dynamically_for_liveness():
    cmd = build_watch_command(SENTINEL, pidfile_path("run123", SDIR))
    assert 'PIDFILE="/tmp/polyjarvis/sentinels/pid_run123"' in cmd
    assert 'cat "$PIDFILE"' in cmd          # read live, not a frozen numeric PID
    assert 'kill -0 "$PID"' in cmd
    assert "PROCESS_DEAD_NO_SENTINEL" in cmd


def test_command_degrades_to_pure_wait_without_pidfile():
    """Empty pidfile must not trip the liveness branch (no false PROCESS_DEAD)."""
    cmd = build_watch_command(SENTINEL, "")
    assert 'PIDFILE=""' in cmd
    assert '[ -n "$PID" ]' in cmd  # guard requires a non-empty PID → branch inert


def test_runs_complete_immediately_when_sentinel_exists(tmp_path):
    sentinel = tmp_path / "done.json"
    sentinel.write_text('{"run_id":"x","status":"completed"}')
    cmd = build_watch_command(str(sentinel), str(tmp_path / "pid_x"))
    out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=10)
    assert out.returncode == 0
    assert "RUN_COMPLETE" in out.stdout
    assert '"status":"completed"' in out.stdout


def test_emits_process_dead_when_pid_gone_and_no_sentinel(tmp_path):
    sentinel = tmp_path / "missing.json"  # never created
    pf = tmp_path / "pid_x"
    dead = subprocess.Popen(["sleep", "30"])
    dead.kill()
    dead.wait()  # reap → kill -0 on this pid now fails
    pf.write_text(str(dead.pid))
    cmd = build_watch_command(str(sentinel), str(pf))
    out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=10)
    assert out.returncode == 3
    assert "PROCESS_DEAD_NO_SENTINEL" in out.stdout
    assert "RUN_COMPLETE" not in out.stdout


def test_pidfile_dollar_pid_survives_setsid_nohup(tmp_path):
    """Regression for the original bug: $! captured the short-lived setsid launcher
    (dead within ~1 s). The long-lived wrapper's own $$ written to a pidfile must
    be alive and kill -0-able while the inner command runs."""
    pf = tmp_path / "pid_x"
    subprocess.run(
        ["bash", "-c", f"setsid nohup bash -c 'echo $$ > {pf}; sleep 5' </dev/null & disown"],
        check=True,
    )
    subprocess.run(["sleep", "1"])
    pid = pf.read_text().strip()
    assert pid.isdigit()
    alive = subprocess.run(["kill", "-0", pid]).returncode
    assert alive == 0, "wrapper $$ should be alive 1 s in (the bug had it dead)"


def test_progress_emits_one_line_per_completed_stage(tmp_path):
    """Chains stream a PROGRESS line (with ASCII bar) as each stage finishes —
    strictly once per stage, never displacing the terminal RUN_COMPLETE."""
    prog = tmp_path / "p.jsonl"
    prog.write_text(
        '{"stage":"01_min","status":"running","ts":"t"}\n'
        '{"stage":"01_min","status":"done","ts":"t"}\n'
        '{"stage":"02_npt","status":"running","ts":"t"}\n'
        '{"stage":"02_npt","status":"done","ts":"t"}\n'
    )
    sentinel = tmp_path / "done.json"
    sentinel.write_text('{"status":"completed"}')  # present → loop exits after one emit
    cmd = build_watch_command(str(sentinel), "", str(prog), n_stages=9)
    out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=10)
    lines = [l for l in out.stdout.splitlines() if l.startswith("PROGRESS")]
    assert len(lines) == 2  # exactly one per done stage, not per JSONL line
    assert "1/9 done: 01_min" in lines[0]
    assert "2/9 done: 02_npt" in lines[1]
    assert "[#--------]" in lines[0]  # ASCII bar reflects 1 of 9
    assert "RUN_COMPLETE" in out.stdout


def test_progress_clean_when_no_stage_done_yet(tmp_path):
    """First stage still running (zero 'done' lines): no PROGRESS lines and no
    stderr noise. Guards the grep -c zero-match arithmetic bug."""
    prog = tmp_path / "p.jsonl"
    prog.write_text('{"stage":"01_min","status":"running","ts":"t"}\n')
    sentinel = tmp_path / "done.json"
    sentinel.write_text('{"status":"completed"}')  # present → one emit then exit
    cmd = build_watch_command(str(sentinel), "", str(prog), n_stages=9)
    out = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, timeout=10)
    assert out.returncode == 0
    assert not [l for l in out.stdout.splitlines() if l.startswith("PROGRESS")]
    assert "integer expression expected" not in out.stderr
    assert out.stderr.strip() == ""


def test_no_progress_for_single_runs():
    """A run without a progress_file (single script) emits no PROGRESS lines."""
    cmd = build_watch_command(SENTINEL, pidfile_path("run123", SDIR))
    assert 'PROGRESS=""' in cmd
    assert "NSTAGES=0" in cmd


def test_chain_script_writes_pidfile_and_sentinel_consistently():
    """Chain pidfile/sentinel are written by the nohup'd shell (crash-safe), and
    the pidfile path the chain writes MUST equal the path the watch command reads."""
    pytest.importorskip("mcp")  # server.py needs fastmcp; skip where unavailable
    import server

    chain_id = "abcd1234"
    script = server._build_chain_script(
        chain_id,
        [{"name": "01_min", "script": "min.in", "work_dir": "/tmp/wd", "log_file": "m.log"}],
        mpi=2,
        gpu_ids="0,1",
    )
    expected_pidfile = pidfile_path(chain_id, server.SENTINEL_DIR)

    assert f"mkdir -p {server.SENTINEL_DIR}" in script
    assert f"PIDFILE={expected_pidfile}" in script
    assert 'echo $$ > "$PIDFILE"' in script   # writer side
    assert "sentinel_ok" in script            # success tail
    assert "sentinel_fail 01_min" in script   # stage-failure branch

    # reader (watch command) must compute the IDENTICAL pidfile path
    cmd = build_watch_command(str(server.SENTINEL_DIR / f"done_{chain_id}.json"), expected_pidfile)
    assert f'PIDFILE="{expected_pidfile}"' in cmd

    # generated script must be valid bash
    syntax = subprocess.run(["bash", "-n"], input=script, text=True, capture_output=True)
    assert syntax.returncode == 0, syntax.stderr
