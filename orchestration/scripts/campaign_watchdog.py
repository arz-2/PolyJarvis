#!/usr/bin/env python3
"""Detect PolyJarvis campaigns whose orchestrating process died mid-run (or that reached
escalation_required with no recovery agent ever consulted) and resume them unattended.

Scope: this script only revives a run when doing so is provably safe under this codebase's
own already-bounded recovery machinery (MAX_AGENT_DECISIONS=2, workflow_engine.py) -- it
never invents new authority of its own. Every run under data/ is classified into exactly one
of three outcomes, decided from data/<run>/workflow_state.json plus a live-process check
(never workflow_state.json's own possibly-stale status/attempt markers alone -- a killed
process leaves those exactly as they were at the moment of death):

  - SKIP, live process -- something (a human session, a previously-launched watchdog resume)
    is already working this run. Never double-launch. If the currently-running attempt's own
    work directory hasn't had a file touched in --stale-minutes (default 60), this is
    additionally flagged `possibly_hung: true` with the staleness detail -- reported only,
    never acted on. Killing a live GPU-holding simulation unattended is a real, hard-to-reverse
    action (lost work, corrupted output, an orphaned GPU claim); deciding whether to intervene
    on a specific hung run is a human call, not this script's.
  - SKIP, terminal and settled -- "accepted" (done), "failed" (the recovery agent already gave
    a considered `stop` -- a genuine human judgment call this script must not second-guess),
    or "escalation_required"/"unresolved" with agent_escalations already at
    MAX_AGENT_DECISIONS (the ladder is genuinely exhausted, not just under-tried).
  - RESUME -- no live process and not one of the above: either an attempt is still marked
    "running" on disk (the orchestrating process died mid-stage), the run stalled between
    stages, it never made any progress, or it reached escalation_required/unresolved with
    agent-decision budget still unspent (most commonly because it was run once through bare
    `run_campaign.py --plan ...`, which has no way to wire a recovery agent at all). All of
    these are safe to just resume: WorkflowEngine's own reconcile_inputs() self-heals a stale
    "running" attempt marker to "incomplete" on the next construction (see
    workflow_engine.py's _load_or_create_state), and MAX_AGENT_DECISIONS is durable in
    workflow_state.json across process restarts, so a run that already exhausted it is caught
    by the SKIP branch above rather than retried again here.

Resumes go through `agent_api.py resume <run_name> --recovery-agent-command ...` -- never bare
`run_campaign.py --plan ...` (documented in recover.md's own "Session reattach" section, but
that entry point has no --recovery-agent-command flag at all: any escalation-worthy finding
during a resume through it dead-ends immediately with no agent ever consulted) -- so a revived
run gets the same real agent coverage a live orchestrating session would have given it.

Intended to run from cron/systemd-timer, e.g. every 10-15 minutes:
    */15 * * * *  cd /home/arz2/PolyJarvis_v2 && \\
                  mcp-servers/.venv/bin/python orchestration/scripts/campaign_watchdog.py \\
                  >> data/_watchdog_logs/watchdog.jsonl 2>&1
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from run_campaign import REPO_ROOT, VENV_PY  # noqa: E402
from workflow_engine import MAX_AGENT_DECISIONS  # noqa: E402


RECOVERY_AGENT_COMMAND = f"{VENV_PY} {SCRIPT_DIR / 'recovery_agent_cli.py'}"
ORCHESTRATOR_SCRIPTS = ("run_campaign.py", "agent_api.py", "scientific_control.py")
TERMINAL_SETTLED = frozenset({"accepted", "failed"})
# run_lammps_chain launches a detached (setsid nohup) shell that keeps running and finishes
# independently of the orchestrating Python process (see do_equil_and_check's "Reattach guard"
# comment in run_campaign.py) -- a dead orchestrator does NOT imply a dead simulation. A
# process whose args merely reference this run's directory for read-only inspection (a `cat`/
# `grep` a human or Claude session ran while looking at state) must not count as "live work",
# or the watchdog would never resume anything anyone had recently looked at.
READ_ONLY_INSPECTION_VERBS = frozenset({
    "cat", "grep", "find", "tail", "head", "ls", "wc", "jq", "ps", "less", "more", "sed", "awk",
    "diff", "vi", "vim", "nano", "code",
})
DEFAULT_STALE_MINUTES = 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _live_pids_for_run(run_name: str, ps_output: Optional[str] = None) -> list[int]:
    """OS-level liveness for `run_name` -- never workflow_state.json's own status, which can
    only ever report what was true when a process last wrote it (exactly the stale picture a
    killed process leaves behind). Matches any process actually operating on
    data/<run_name>/ -- the orchestrating Python script AND any detached LAMMPS/EMC job it
    launched that outlives it -- except bare read-only inspection commands.

    Excludes this script's own process line (and any shell wrapping it, e.g. a Bash-tool
    session's `bash -c 'eval ...'`): when invoked as `campaign_watchdog.py --run-name X`,
    the watchdog's OWN command line -- and the shell wrapper's, which embeds the full inner
    command as one string -- literally contains the run_name token, and would otherwise
    self-match as "X is live" on every single scoped invocation. A genuine live orchestrator
    or simulation process for a run never has "campaign_watchdog.py" on its own command
    line, so this exclusion carries no risk of masking real work."""
    if ps_output is None:
        try:
            ps_output = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True,
                                       text=True, check=True).stdout
        except (OSError, subprocess.CalledProcessError):
            return []
    marker = f"data/{run_name}/"
    pids = []
    for line in ps_output.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        pid_str, _, args = line.partition(" ")
        tokens = args.split()
        if not tokens:
            continue
        if "campaign_watchdog.py" in args:
            continue
        is_orchestrator = any(script in args for script in ORCHESTRATOR_SCRIPTS)
        references_run = marker in args or run_name in tokens
        if not references_run:
            continue
        verb = Path(tokens[0]).name
        if not is_orchestrator and verb in READ_ONLY_INSPECTION_VERBS:
            continue
        try:
            pids.append(int(pid_str))
        except ValueError:
            continue
    return pids


def _running_attempt_staleness(run_dir: Path, state: dict[str, Any],
                                now: Optional[float] = None) -> Optional[dict[str, Any]]:
    """How long since any file under the currently in-flight attempt's work directory was
    last modified -- the same "is this actually still making progress" question a human would
    ask by tailing the LAMMPS log, just via mtime instead of trusting the process merely
    exists. Only meaningful while a live process was already found for this run; returns None
    (nothing to report) if no attempt is marked "running" or its work directory has no files
    yet (e.g. still inside minimize, before any stage log exists)."""
    now = time.time() if now is None else now
    for stage, record in (state.get("stages") or {}).items():
        attempts = record.get("attempts") or []
        if not attempts or attempts[-1].get("status") != "running":
            continue
        attempt_id = attempts[-1].get("attempt_id")
        if not attempt_id:
            continue
        work_dir = run_dir / "attempts" / stage / attempt_id / "work"
        if not work_dir.is_dir():
            continue
        newest = max((f.stat().st_mtime for f in work_dir.rglob("*") if f.is_file()),
                     default=None)
        if newest is None:
            continue
        age_seconds = now - newest
        return {
            "stage": stage, "attempt_id": attempt_id, "age_seconds": round(age_seconds, 1),
            "newest_mtime": datetime.fromtimestamp(newest, tz=timezone.utc).isoformat(),
        }
    return None


def _orphaned_stage(state: dict[str, Any]) -> Optional[str]:
    for stage, record in (state.get("stages") or {}).items():
        attempts = record.get("attempts") or []
        if attempts and attempts[-1].get("status") == "running":
            return stage
    return None


def classify(run_dir: Path, ps_output: Optional[str] = None,
             stale_minutes: float = DEFAULT_STALE_MINUTES) -> dict[str, Any]:
    run_name = run_dir.name
    state_path = run_dir / "workflow_state.json"
    if not state_path.is_file():
        return {"run_name": run_name, "action": "skip", "reason": "no_workflow_state"}
    try:
        state = json.loads(state_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return {"run_name": run_name, "action": "skip", "reason": f"unreadable_state: {exc}"}

    live_pids = _live_pids_for_run(run_name, ps_output)
    if live_pids:
        result = {"run_name": run_name, "action": "skip", "reason": "live_process",
                  "pids": live_pids}
        staleness = _running_attempt_staleness(run_dir, state)
        if staleness is not None:
            result["staleness"] = staleness
            result["possibly_hung"] = staleness["age_seconds"] > stale_minutes * 60
        return result

    status = state.get("status")
    if status == "accepted":
        return {"run_name": run_name, "action": "skip", "reason": "already_accepted"}
    if status == "failed":
        return {"run_name": run_name, "action": "skip",
                "reason": "agent_returned_stop_needs_human"}
    if status in ("escalation_required", "unresolved"):
        spent = len(state.get("agent_escalations") or [])
        if spent >= MAX_AGENT_DECISIONS:
            return {"run_name": run_name, "action": "skip",
                    "reason": "agent_decision_budget_exhausted_needs_human",
                    "agent_escalations_spent": spent}
        return {"run_name": run_name, "action": "resume",
                "reason": "escalation_required_with_agent_budget_remaining",
                "agent_escalations_spent": spent}

    # No live process and no settled terminal status: the orchestrating process died mid-stage
    # (an attempt still marked "running"), stalled between stages, or never made progress at
    # all. All safe to resume -- nothing conclusive happened.
    orphaned = _orphaned_stage(state)
    return {"run_name": run_name, "action": "resume",
            "reason": "orphaned_in_flight_attempt" if orphaned else "incomplete_no_live_process",
            "stage": orphaned}


def resume(run_name: str, repo_root: Path, log_dir: Path) -> dict[str, Any]:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{run_name}.log"
    cmd = [str(VENV_PY), str(SCRIPT_DIR / "agent_api.py"), "resume", run_name,
           "--recovery-agent-command", RECOVERY_AGENT_COMMAND]
    with log_path.open("a") as log_file:
        log_file.write(f"\n=== watchdog resume {_now()} ===\n{' '.join(cmd)}\n")
        log_file.flush()
        proc = subprocess.Popen(cmd, stdout=log_file, stderr=subprocess.STDOUT,
                                cwd=str(repo_root), start_new_session=True)
    return {"run_name": run_name, "pid": proc.pid, "log_path": str(log_path)}


def scan(repo_root: Path, run_names: Optional[list[str]] = None,
         stale_minutes: float = DEFAULT_STALE_MINUTES) -> list[dict[str, Any]]:
    data_dir = repo_root / "data"
    if run_names:
        run_dirs = [data_dir / name for name in run_names]
    else:
        run_dirs = (sorted(p for p in data_dir.iterdir() if p.is_dir() and not p.name.startswith("_"))
                   if data_dir.is_dir() else [])
    try:
        ps_output = subprocess.run(["ps", "-eo", "pid,args"], capture_output=True,
                                   text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        ps_output = ""
    return [classify(run_dir, ps_output, stale_minutes) for run_dir in run_dirs
           if run_dir.is_dir()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--dry-run", action="store_true", help="classify and report only")
    parser.add_argument("--run-name", action="append", dest="run_names",
                        help="limit the scan to this run (repeatable); default scans every "
                             "data/<run> with a workflow_state.json")
    parser.add_argument("--stale-minutes", type=float, default=DEFAULT_STALE_MINUTES,
                        help="flag (never act on) a live run whose current attempt hasn't "
                             "touched a file in this many minutes (default %(default)s)")
    args = parser.parse_args()
    repo_root = Path(args.repo_root)

    classifications = scan(repo_root, args.run_names, args.stale_minutes)
    resumed = []
    for entry in classifications:
        if entry["action"] == "resume" and not args.dry_run:
            resumed.append({**entry,
                            "launched": resume(entry["run_name"], repo_root,
                                               repo_root / "data" / "_watchdog_logs")})
    # Reported only -- see the module docstring on why the watchdog never acts on this itself.
    possibly_hung = [entry for entry in classifications if entry.get("possibly_hung")]
    print(json.dumps({
        "at": _now(), "scanned": len(classifications), "dry_run": args.dry_run,
        "classifications": classifications, "resumed": resumed, "possibly_hung": possibly_hung,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()
