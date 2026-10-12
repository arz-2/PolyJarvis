"""Extracts the wall/compute-time axis for both arms.

PolyJarvis side (field shapes verified live against data/PE1):
- Orchestration wall-clock: diff `started_at`/`finished_at` across every attempt in
  data/<run>/workflow_state.json's `stages.*.attempts[]` -- this intentionally includes
  queueing/recovery latency, since that cost is part of what adaptive gating spends.
- Pure MD compute time: parse the `Total wall time: H:MM:SS` footer LAMMPS writes on
  clean exit (mcp-servers/mcp-lammps-engine/analysis_scripts/analysis_utils.parse_lammps_wall_time,
  added alongside the existing parse_lammps_log rather than changing its contract).
  Empirically (checked live against data/PE1) this footer is present in only a small
  minority of *.log files -- most stage invocations here never reach that clean-exit
  print, so the practical fallback (file-mtime diffing: latest mtime minus earliest
  mtime among a stage's own files) is the dominant path, not a rare edge case. Every
  reported figure records which method produced it.

RadonPy side: reads the harness's own timestamps.json (radonpy_runner.py), which
brackets each phase (qm, eq) with its own started_at/finished_at since RadonPy's sample
scripts write no timing data of their own.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from .schema import WallTimeBlock

_ANALYSIS_SCRIPTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"
)
if str(_ANALYSIS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_ANALYSIS_SCRIPTS_DIR))

from analysis_utils import parse_lammps_wall_time  # noqa: E402


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _stage_compute_time(work_dir: Path) -> tuple[float, str]:
    """Returns (seconds, method) for one stage's `work/` directory: sums each
    immediate subdirectory's own footer-or-mtime-fallback duration."""
    if not work_dir.is_dir():
        return 0.0, "unknown"

    total = 0.0
    any_fallback = False
    any_data = False
    for substage_dir in sorted(p for p in work_dir.iterdir() if p.is_dir()):
        files = [f for f in substage_dir.iterdir() if f.is_file()]
        if not files:
            continue
        footer_seconds = None
        for f in files:
            if f.suffix == ".log":
                footer_seconds = parse_lammps_wall_time(f)
                if footer_seconds is not None:
                    break
        if footer_seconds is not None:
            total += footer_seconds
            any_data = True
        else:
            mtimes = [f.stat().st_mtime for f in files]
            total += max(mtimes) - min(mtimes)
            any_fallback = True
            any_data = True

    if not any_data:
        return 0.0, "unknown"
    return total, ("mtime_fallback" if any_fallback else "footer")


def extract_polyjarvis_wall_time(run_dir: Path) -> WallTimeBlock:
    block = WallTimeBlock()

    workflow_path = run_dir / "workflow_state.json"
    if workflow_path.is_file():
        workflow = json.loads(workflow_path.read_text())
        starts, ends = [], []
        for stage_record in (workflow.get("stages") or {}).values():
            for attempt in stage_record.get("attempts") or []:
                if attempt.get("started_at"):
                    starts.append(_parse_iso(attempt["started_at"]))
                if attempt.get("finished_at"):
                    ends.append(_parse_iso(attempt["finished_at"]))
        if starts and ends:
            block.orchestration_wall_time_s = (max(ends) - min(starts)).total_seconds()

    total_compute = 0.0
    methods_used = set()
    attempts_root = run_dir / "attempts"
    if attempts_root.is_dir():
        for stage_dir in attempts_root.iterdir():
            if stage_dir.name == "build":
                continue  # build has no LAMMPS MD compute time
            for attempt_dir in stage_dir.glob("attempt-*"):
                work_dir = attempt_dir / "work"
                seconds, method = _stage_compute_time(work_dir)
                total_compute += seconds
                if method != "unknown":
                    methods_used.add(method)

    block.md_compute_time_s = total_compute if methods_used else None
    block.md_compute_time_method = (
        "mtime_fallback" if "mtime_fallback" in methods_used
        else ("footer" if methods_used else None)
    )
    block.build_time_s = None  # EMC build timing is not separately logged; see note below
    return block


def extract_radonpy_wall_time(harness_root: Path) -> WallTimeBlock:
    block = WallTimeBlock()
    timestamps_path = harness_root / "timestamps.json"
    if not timestamps_path.is_file():
        return block

    data = json.loads(timestamps_path.read_text())
    phase_seconds = {}
    for phase in data.get("phases", []):
        if phase.get("started_at") and phase.get("finished_at"):
            seconds = (_parse_iso(phase["finished_at"]) - _parse_iso(phase["started_at"])).total_seconds()
            phase_seconds[phase["phase"]] = seconds

    block.qm_time_s = phase_seconds.get("qm")
    block.md_compute_time_s = phase_seconds.get("eq")
    block.md_compute_time_method = "phase_bracket"
    block.orchestration_wall_time_s = sum(phase_seconds.values()) if phase_seconds else None
    return block
