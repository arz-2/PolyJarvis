#!/usr/bin/env python3
"""Run a PolyJarvis campaign end to end with no live Claude Code session.

    mcp-servers/.venv/bin/python orchestration/langgraph/run_graph.py \
        --run-name PS1 --smiles '*CC(*)c1ccccc1' --properties density,tg \
        --goal 'density and Tg for polystyrene' \
        --max-gpu-hours 40 --deadline-hours 24

Blocking. Streams one NDJSON event per node to stdout (interleaved with the campaign's own
output; filter on the "event" key) and exits with a status code from state.EXIT_CODES:

    0  accepted              6  classify_error / plan_error / materialize_error
    2  escalation_required   7  d01_refusal    (no force field can build this chemistry)
    3  failed                8  locked         (another driver holds this run)
    4  deadline_exceeded     5  cost_exceeded / cost_unknown

Exit 2 and 3 are TERMINAL, not retryable -- the engine's two recovery-agent calls are
already spent by then (see graph.py). Exit 4 and 8 leave the campaign resumable: re-invoke
with --resume.

Re-execs into mcp-servers/.venv if started elsewhere, the same guard run_campaign.py uses:
execute imports nothing from the MCP servers itself, but agent_api does, and a driver
started under the wrong interpreter would fail deep inside a subprocess instead of here.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent.parent
VENV_PY = REPO_ROOT / "mcp-servers" / ".venv" / "bin" / "python"
sys.path.insert(0, str(HERE))


def _reexec_into_venv() -> None:
    if VENV_PY.is_file() and Path(sys.executable).resolve() != VENV_PY.resolve():
        os.execv(str(VENV_PY), [str(VENV_PY), str(Path(__file__).resolve()), *sys.argv[1:]])


class RunLock:
    """An O_EXCL lock on data/<run>/raw/.graph.lock.

    make_deterministic_plan refuses to clobber an existing plan, but materialize rewrites it
    in place, so two drivers on one run_name would interleave writes to run_plan.json.
    control_state.json is a session marker, not a lock, and cannot serve here.
    A lock whose PID is gone is stale and reclaimed -- a killed driver must not wedge a run.
    """

    def __init__(self, run_dir: Path):
        self.path = run_dir / "raw" / ".graph.lock"
        self.held = False

    def _stale(self) -> bool:
        try:
            pid = json.loads(self.path.read_text()).get("pid")
        except (json.JSONDecodeError, OSError):
            return True
        if not isinstance(pid, int):
            return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False       # alive, owned by someone else
        return False

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(2):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                if not self._stale():
                    return False
                self.path.unlink(missing_ok=True)
                continue
            with os.fdopen(fd, "w") as fh:
                json.dump({"pid": os.getpid(),
                           "started_at": datetime.now(timezone.utc).isoformat()}, fh)
            self.held = True
            return True
        return False

    def release(self) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.release()


def _progress_poller(run_dir: Path, stop: threading.Event, interval: float = 20.0) -> None:
    """Per-stage visibility without owning anything.

    run_campaign has no stage-selectable entry point -- its CLI takes a plan, never a stage,
    and sequencing lives inside WorkflowEngine. Rather than adding one, this reads
    workflow_state.json, which the engine already maintains. It never writes, never signals,
    and never routes; it only narrates.
    """
    path = run_dir / "workflow_state.json"
    last: dict[str, str] = {}
    while not stop.wait(interval):
        try:
            stages = (json.loads(path.read_text()).get("stages") or {})
        except (OSError, json.JSONDecodeError):
            continue
        for stage, record in stages.items():
            status = record.get("status")
            if status and last.get(stage) != status:
                last[stage] = status
                print(json.dumps({"event": "stage_progress", "stage": stage, "status": status,
                                  "attempts": len(record.get("attempts") or []),
                                  "at": datetime.now(timezone.utc).isoformat()}), flush=True)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run-name", required=True)
    p.add_argument("--smiles", required=True)
    p.add_argument("--goal", default="")
    p.add_argument("--properties", default="density,tg,bulk_modulus")
    p.add_argument("--repo-root", default=str(REPO_ROOT))
    p.add_argument("--resume", action="store_true",
                   help="pick up where data/<run>/ left off (this is also automatic)")
    p.add_argument("--dry-run", action="store_true",
                   help="plan, guard and stop; execute is never entered")
    p.add_argument("--no-llm", action="store_true",
                   help="deterministic arm: --baseline plan, no critic, no adjudicator")
    p.add_argument("--max-gpu-hours", type=float, default=None,
                   help="refuse to execute above this priced cost (a LOWER bound -- see guards)")
    p.add_argument("--allow-unpriced", action="store_true",
                   help="proceed when cost_estimate carries no total at all")
    p.add_argument("--deadline-hours", type=float, default=None,
                   help="soft stop between nodes; never kills a running stage")
    args = p.parse_args()

    from graph import build_graph
    from state import EXIT_CODES, RESUMABLE_STATUSES

    repo_root = Path(args.repo_root).resolve()
    run_dir = repo_root / "data" / args.run_name
    deadline = (datetime.now(timezone.utc) + timedelta(hours=args.deadline_hours)).isoformat() \
        if args.deadline_hours else None

    initial = {
        "run_name": args.run_name, "smiles": args.smiles, "goal": args.goal,
        "properties": [x.strip() for x in args.properties.split(",") if x.strip()],
        "repo_root": str(repo_root), "dry_run": args.dry_run, "no_llm": args.no_llm,
        "resume": args.resume, "max_gpu_hours": args.max_gpu_hours,
        "allow_unpriced": args.allow_unpriced, "deadline_at": deadline, "events": [],
    }

    with RunLock(run_dir) as lock:
        if not lock.acquire():
            print(json.dumps({"event": "stop", "status": "locked",
                              "detail": f"another driver holds {lock.path}"}), flush=True)
            return EXIT_CODES["locked"]

        stop = threading.Event()
        poller = threading.Thread(target=_progress_poller, args=(run_dir, stop), daemon=True)
        poller.start()
        try:
            final = build_graph().invoke(initial, {"recursion_limit": 50})
        finally:
            stop.set()

    status = final.get("status") or final.get("workflow_status") or "failed"
    if args.dry_run and status == "skipped":
        status = "accepted"
    code = EXIT_CODES.get(status, 1)
    print(json.dumps({
        "event": "done", "status": status, "exit_code": code,
        "run_name": args.run_name, "polymer_class": final.get("polymer_class"),
        "class_source": final.get("class_source"), "plan_path": final.get("plan_path"),
        "confidence": final.get("confidence"), "plan_mode": final.get("plan_mode"),
        "gpu_hours": final.get("cost_gpu_hours"), "unpriced": final.get("cost_unpriced"),
        "critic_verdict": final.get("critic_verdict"), "stage": final.get("workflow_stage"),
        "finding": final.get("finding_code"), "detail": final.get("detail"),
        "resumable": status in RESUMABLE_STATUSES,
    }, default=str), flush=True)
    return code


if __name__ == "__main__":
    _reexec_into_venv()
    sys.exit(main())
