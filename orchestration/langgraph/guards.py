#!/usr/bin/env python3
"""Cost and deadline guards — the only things standing between an unattended graph and the
GPUs, now that there is no human confirmation step.

Two guards, deliberately different in kind:

  check_cost      a REFUSAL. Reads the plan's own cost_estimate and stops the graph before
                  execute if the priced work exceeds the ceiling. Cannot be a clearance --
                  see below.
  deadline        a soft stop, checked BETWEEN nodes. It never kills anything. See
                  deadline_expired for why a hard kill would actively corrupt state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _now() -> datetime:
    return datetime.now(timezone.utc)


def deadline_expired(state: dict[str, Any]) -> bool:
    """Has --deadline-hours elapsed?

    Checked at the top of every node, and NOTHING is ever signalled or killed on the way
    out. That is not timidity, it is correctness: LAMMPS is launched detached
    (`setsid nohup ... & disown`, mcp-lammps-engine/server.py) so it survives the driver,
    while run_campaign's gpu_claim context manager releases the hardware_runtime.py ledger
    entry on SIGTERM. Killing the driver would therefore mark the GPU free in the ledger
    while LAMMPS is still running on it, and the next claim would double-book that card.

    So the deadline bounds THIS DRIVER, not the campaign. In practice it stops the graph
    before it submits; a pass already in flight runs to completion and the campaign stays
    resumable. Note campaign_watchdog.py, if scheduled, will itself resume a run left this
    way -- deliberately not special-cased here, because teaching the watchdog a new skip
    rule widens its blast radius for a scheduling nicety.
    """
    raw = state.get("deadline_at")
    if not raw:
        return False
    return _now() >= datetime.fromisoformat(raw)


def check_cost(plan: dict[str, Any], *, max_gpu_hours: float | None,
               allow_unpriced: bool = False, priced: bool = True) -> dict[str, Any]:
    """Decide whether this plan may proceed to execution.

    Returns {"ok": True, ...} or {"ok": False, "status": ..., "detail": ...}.

    `priced=False` says the plan is not expected to carry a cost yet -- a scaffold straight
    out of `run-plan` has cost_estimate: null, because pricing happens in materialize_plan
    after overrides and the final cell size are known. In that case an absent total is
    normal and passes; only an already-over-ceiling number refuses. The binding check is
    the priced one after materialize.

    The subtlety worth stating plainly: cost_estimate.total_gpu_hours is a documented LOWER
    BOUND, not an estimate. `unpriced_stages` routinely holds equil (whose stage-length
    knobs default to None and are resolved inside the MCP engine, not from decided_params)
    and often murnaghan. A ceiling test against a lower bound is only ever sound in one
    direction: if the lower bound already exceeds the ceiling, refusing is certainly right;
    if it does not, that is NOT evidence the real cost fits. So this refuses loudly and
    never clears silently -- an unpriced plan stops unless the caller says otherwise, and
    even an admitted one carries the caveat forward into the event stream.
    """
    estimate = plan.get("cost_estimate") or {}

    if not estimate and not priced:
        return {"ok": True, "gpu_hours": None, "unpriced": [],
                "note": "not priced yet; materialize computes cost_estimate"}

    if "error" in estimate:
        return {"ok": False, "status": "cost_unknown",
                "detail": f"cost_estimate could not be computed: {estimate['error']}"}

    total = estimate.get("total_gpu_hours")
    unpriced = [u.get("stage", u) if isinstance(u, dict) else u
                for u in (estimate.get("unpriced_stages") or [])]

    if total is None:
        if not priced:
            return {"ok": True, "gpu_hours": None, "unpriced": unpriced,
                    "note": "not priced yet; materialize computes cost_estimate"}
        if not allow_unpriced:
            return {"ok": False, "status": "cost_unknown",
                    "detail": ("cost_estimate carries no total_gpu_hours, so the ceiling "
                               "cannot be applied at all. Re-run with --allow-unpriced to "
                               "proceed anyway; the wall-clock deadline is then the only "
                               "bound on this run."),
                    "unpriced": unpriced}
        return {"ok": True, "gpu_hours": None, "unpriced": unpriced,
                "note": "no total_gpu_hours; proceeding on --allow-unpriced"}

    if max_gpu_hours is not None and total > max_gpu_hours:
        return {"ok": False, "status": "cost_exceeded",
                "detail": (f"priced work is {total:.2f} GPU-hours against a ceiling of "
                           f"{max_gpu_hours:.2f}. This is a LOWER bound -- "
                           f"{len(unpriced)} stage(s) are unpriced -- so the real cost is "
                           "higher, not lower."),
                "gpu_hours": total, "unpriced": unpriced}

    return {"ok": True, "gpu_hours": total, "unpriced": unpriced,
            "note": ("total_gpu_hours is a LOWER bound; unpriced stages are excluded"
                     if unpriced else None)}


def check_d01_admissible(plan: dict[str, Any]) -> dict[str, Any]:
    """Refuse before spending anything if no force field can build this chemistry.

    D-01's `admissible` is measured by materialize_plan's own force-field probe -- a real
    EMC trial build -- and an empty list means every registered field was measured to fail
    this repeat unit. The skill tells a human to stop there; this is that instruction
    mechanised, placed before the critic so an unbuildable polymer costs no model spend.
    """
    decisions = plan.get("decisions") or []
    if not decisions:
        return {"ok": True}
    d01 = decisions[0]
    admissible = d01.get("admissible")
    if admissible is not None and len(admissible) == 0:
        return {"ok": False, "status": "d01_refusal",
                "detail": (f"D-01 admissible is empty for {plan.get('smiles')!r}: no "
                           "registered EMC field typed this repeat unit in a real trial "
                           f"build. {d01.get('reason', '')}").strip(),
                "decision": d01.get("id", "D-01_ff")}
    return {"ok": True, "admissible": admissible}


def read_plan(plan_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(plan_path).read_text())
