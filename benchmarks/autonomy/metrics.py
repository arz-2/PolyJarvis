#!/usr/bin/env python3
"""
Shared metrics schema for the autonomy-evidence benchmark (R1M1 / M7 / M11).

Both arms (SCRIPT baseline and AGENT) and the recovery harness emit the same
JSON shape so results are directly comparable. Process metrics only — human
interventions, wall-clock, recovery events, terminal state — never accuracy
(per the design: we claim orchestration/recovery, not improved numbers).
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass
class RecoveryEvent:
    fault: str                  # error_class / fault id
    prescripted: bool           # was the recovery in recover.md (Tier 1)?
    resolved: bool              # did the recovery succeed?
    attempts: int = 1           # attempts incl. failures (R1M11 asks for this)
    note: str = ""


@dataclass
class RunMetrics:
    arm: str                    # "script" | "agent"
    system: str                 # e.g. "PMMA" or "PHYC-smoke"
    polymer_class: str = ""
    seed: Optional[int] = None  # EMC packing / velocity seed used
    interventions: int = 0      # human interventions required
    wall_clock_s: float = 0.0
    terminal_state: str = "unknown"   # completed | stalled | wrong_but_undetected | error
    recovery_events: List[RecoveryEvent] = field(default_factory=list)
    stages_completed: List[str] = field(default_factory=list)
    smoke: bool = False
    notes: str = ""

    # --- timing helper ---
    _t0: Optional[float] = field(default=None, repr=False, compare=False)

    def start(self) -> "RunMetrics":
        self._t0 = time.time()
        return self

    def stop(self) -> "RunMetrics":
        if self._t0 is not None:
            self.wall_clock_s = round(time.time() - self._t0, 3)
        return self

    def add_recovery(self, ev: RecoveryEvent) -> None:
        self.recovery_events.append(ev)

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("_t0", None)
        return d

    def write(self, out_dir: Optional[Path] = None) -> Path:
        out_dir = Path(out_dir) if out_dir else RESULTS_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{self.system}_{self.arm}.json"
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        return path


def recovery_success_rate(events: List[RecoveryEvent]) -> Optional[float]:
    """Overall recovery success rate across events (None if no events)."""
    if not events:
        return None
    return round(sum(1 for e in events if e.resolved) / len(events), 4)
