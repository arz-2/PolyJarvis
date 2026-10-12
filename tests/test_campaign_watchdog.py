import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import campaign_watchdog as watchdog  # noqa: E402
from workflow_engine import MAX_AGENT_DECISIONS  # noqa: E402


PS_HEADER = "  PID ARGS\n"


def _ps(*lines: str) -> str:
    return PS_HEADER + "\n".join(lines)


def _write_state(run_dir: Path, **fields) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "stages": {"build": {"status": "accepted", "attempts": [{"status": "accepted"}]},
                  "equilibration": {"status": "pending", "attempts": []}},
        "agent_escalations": [],
    }
    state.update(fields)
    (run_dir / "workflow_state.json").write_text(json.dumps(state))


def test_live_pids_matches_orchestrator_process():
    ps_output = _ps("100 /venv/bin/python orchestration/scripts/run_campaign.py "
                    "--plan data/PP/raw/run_plan.json")
    assert watchdog._live_pids_for_run("PP", ps_output) == [100]


def test_live_pids_matches_detached_simulation_process():
    """A LAMMPS chain outlives the orchestrator that launched it -- the watchdog must not
    treat a dead orchestrator as a dead run when the simulation itself is still running."""
    ps_output = _ps("200 /opt/lammps/bin/lmp -in "
                    "/repo/data/i-PMMA1/attempts/equilibration/"
                    "attempt-0002/work/cool_block_01/cool_block_01.in")
    assert watchdog._live_pids_for_run("i-PMMA1", ps_output) == [200]


def test_live_pids_ignores_read_only_inspection():
    ps_output = _ps("300 cat data/PP/workflow_state.json",
                    "301 grep -n foo data/PP/workflow_state.json")
    assert watchdog._live_pids_for_run("PP", ps_output) == []


def test_live_pids_excludes_its_own_scoped_invocation():
    """A `--run-name X` invocation's own command line (and any shell wrapper around it, e.g.
    a Bash-tool session's `bash -c 'eval ...'`) literally contains the run_name token --
    without this exclusion the watchdog would self-match as "X is live" on every single
    --run-name-scoped call. Real bug hit live 2026-08-26: --run-name a-PS reported a-PS as
    live_process with fresh, already-dead PIDs on every invocation."""
    ps_output = _ps(
        "500 /bin/bash -c eval 'mcp-servers/.venv/bin/python "
        "orchestration/scripts/campaign_watchdog.py --dry-run --run-name a-PS'",
        "501 mcp-servers/.venv/bin/python orchestration/scripts/campaign_watchdog.py "
        "--dry-run --run-name a-PS",
    )
    assert watchdog._live_pids_for_run("a-PS", ps_output) == []


def test_live_pids_ignores_unrelated_runs():
    ps_output = _ps("400 /venv/bin/python orchestration/scripts/run_campaign.py "
                    "--plan data/OtherRun/raw/run_plan.json")
    assert watchdog._live_pids_for_run("PP", ps_output) == []


def test_classify_skips_live_process(tmp_path):
    run_dir = tmp_path / "data" / "PP"
    _write_state(run_dir, status="escalation_required")
    ps_output = _ps("100 /venv/bin/python orchestration/scripts/run_campaign.py "
                    "--plan data/PP/raw/run_plan.json")
    result = watchdog.classify(run_dir, ps_output)
    assert result["action"] == "skip"
    assert result["reason"] == "live_process"


def test_classify_skips_already_accepted(tmp_path):
    run_dir = tmp_path / "data" / "R"
    _write_state(run_dir, status="accepted")
    result = watchdog.classify(run_dir, PS_HEADER)
    assert result == {"run_name": "R", "action": "skip", "reason": "already_accepted"}


def test_classify_skips_a_genuine_stop_decision(tmp_path):
    """status=='failed' means the recovery agent already gave a considered `stop` -- the
    watchdog must never second-guess that human-judgment-call boundary."""
    run_dir = tmp_path / "data" / "R"
    _write_state(run_dir, status="failed")
    result = watchdog.classify(run_dir, PS_HEADER)
    assert result["action"] == "skip"
    assert result["reason"] == "agent_returned_stop_needs_human"


def test_classify_resumes_escalation_required_with_budget_remaining(tmp_path):
    run_dir = tmp_path / "data" / "R"
    _write_state(run_dir, status="escalation_required", agent_escalations=[{"decision": {}}])
    result = watchdog.classify(run_dir, PS_HEADER)
    assert result["action"] == "resume"
    assert result["reason"] == "escalation_required_with_agent_budget_remaining"
    assert result["agent_escalations_spent"] == 1


def test_classify_skips_escalation_required_with_budget_exhausted(tmp_path):
    run_dir = tmp_path / "data" / "R"
    _write_state(run_dir, status="escalation_required",
                 agent_escalations=[{"decision": {}}] * MAX_AGENT_DECISIONS)
    result = watchdog.classify(run_dir, PS_HEADER)
    assert result["action"] == "skip"
    assert result["reason"] == "agent_decision_budget_exhausted_needs_human"


def test_classify_resumes_orphaned_in_flight_attempt(tmp_path):
    run_dir = tmp_path / "data" / "R"
    _write_state(run_dir, stages={
        "build": {"status": "accepted", "attempts": [{"status": "accepted"}]},
        "equilibration": {"status": "running", "attempts": [{"status": "running"}]},
    })
    result = watchdog.classify(run_dir, PS_HEADER)
    assert result["action"] == "resume"
    assert result["reason"] == "orphaned_in_flight_attempt"
    assert result["stage"] == "equilibration"


def test_classify_resumes_stalled_between_stages_with_no_status_and_no_orphan(tmp_path):
    """A process that dies between two stages (last stage accepted, next not yet attempted)
    leaves no "running" attempt anywhere and no terminal top-level status -- must still be
    treated as resumable, not silently ignored."""
    run_dir = tmp_path / "data" / "R"
    _write_state(run_dir)  # default fixture: build accepted, equilibration pending, no status
    result = watchdog.classify(run_dir, PS_HEADER)
    assert result["action"] == "resume"
    assert result["reason"] == "incomplete_no_live_process"
    assert result["stage"] is None


def test_running_attempt_staleness_reports_none_without_a_running_attempt(tmp_path):
    run_dir = tmp_path / "data" / "R"
    run_dir.mkdir(parents=True)
    state = {"stages": {"build": {"status": "accepted", "attempts": [{"status": "accepted"}]}}}
    assert watchdog._running_attempt_staleness(run_dir, state) is None


def test_running_attempt_staleness_reports_none_when_work_dir_has_no_files_yet(tmp_path):
    run_dir = tmp_path / "data" / "R"
    work_dir = run_dir / "attempts" / "equilibration" / "attempt-0001" / "work"
    work_dir.mkdir(parents=True)
    state = {"stages": {"equilibration": {"status": "running",
                                          "attempts": [{"status": "running",
                                                       "attempt_id": "attempt-0001"}]}}}
    assert watchdog._running_attempt_staleness(run_dir, state) is None


def test_running_attempt_staleness_reports_age_of_newest_file(tmp_path):
    run_dir = tmp_path / "data" / "R"
    work_dir = run_dir / "attempts" / "equilibration" / "attempt-0001" / "work"
    work_dir.mkdir(parents=True)
    log_file = work_dir / "npt_final.log"
    log_file.write_text("thermo output")
    stale_mtime = time.time() - 3600  # 1 hour ago
    import os
    os.utime(log_file, (stale_mtime, stale_mtime))
    state = {"stages": {"equilibration": {"status": "running",
                                          "attempts": [{"status": "running",
                                                       "attempt_id": "attempt-0001"}]}}}
    staleness = watchdog._running_attempt_staleness(run_dir, state)
    assert staleness["stage"] == "equilibration"
    assert staleness["attempt_id"] == "attempt-0001"
    assert 3595 <= staleness["age_seconds"] <= 3605


def test_classify_flags_a_live_but_stale_run_without_touching_it(tmp_path):
    run_dir = tmp_path / "data" / "PP"
    work_dir = run_dir / "attempts" / "equilibration" / "attempt-0001" / "work"
    work_dir.mkdir(parents=True)
    log_file = work_dir / "npt_final.log"
    log_file.write_text("thermo output")
    stale_mtime = time.time() - 7200  # 2 hours ago
    import os
    os.utime(log_file, (stale_mtime, stale_mtime))
    _write_state(run_dir, status="escalation_required",
                 stages={"equilibration": {"status": "running",
                                           "attempts": [{"status": "running",
                                                        "attempt_id": "attempt-0001"}]}})
    ps_output = _ps("100 /venv/bin/python orchestration/scripts/run_campaign.py "
                    "--plan data/PP/raw/run_plan.json")
    result = watchdog.classify(run_dir, ps_output, stale_minutes=60)
    assert result["action"] == "skip"
    assert result["reason"] == "live_process"
    assert result["possibly_hung"] is True
    assert result["staleness"]["age_seconds"] > 3600


def test_classify_does_not_flag_a_live_run_that_is_actively_progressing(tmp_path):
    run_dir = tmp_path / "data" / "PP"
    work_dir = run_dir / "attempts" / "equilibration" / "attempt-0001" / "work"
    work_dir.mkdir(parents=True)
    (work_dir / "npt_final.log").write_text("thermo output")  # freshly written, mtime==now
    _write_state(run_dir, status="escalation_required",
                 stages={"equilibration": {"status": "running",
                                           "attempts": [{"status": "running",
                                                        "attempt_id": "attempt-0001"}]}})
    ps_output = _ps("100 /venv/bin/python orchestration/scripts/run_campaign.py "
                    "--plan data/PP/raw/run_plan.json")
    result = watchdog.classify(run_dir, ps_output, stale_minutes=60)
    assert result["action"] == "skip"
    assert result["reason"] == "live_process"
    assert result.get("possibly_hung") is False


def test_classify_skips_missing_workflow_state(tmp_path):
    run_dir = tmp_path / "data" / "NeverStarted"
    run_dir.mkdir(parents=True)
    result = watchdog.classify(run_dir, PS_HEADER)
    assert result == {"run_name": "NeverStarted", "action": "skip", "reason": "no_workflow_state"}
