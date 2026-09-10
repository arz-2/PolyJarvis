#!/usr/bin/env python3
"""R2/R3 -- the controlled fault catalog, keyed to v2 Finding codes.

Round 1's catalog (manuscript/recovery/fault_catalog.py in the sibling checkout) keyed each
fault to a LINE NUMBER in .claude/commands/recover.md. v2 restructured that file and replaced
prose routing with workflow_engine.default_remedies(), so those keys mean nothing here. Every
fault below names a `Finding.code` instead, and `validate()` refuses any fault whose code the
registry does not actually route or that no producer mints -- 15 of the 42 routed codes have
no producer, so a fault designed around one would fire nothing and silently measure nothing.

TWO DESIGN RULES, both about honesty and both about cost:

  * Inject at the GATE, not the physics, wherever possible. Tightening a threshold so a
    healthy trajectory fails it exercises the identical remedy path for minutes of GPU
    instead of hours. `physics: False` marks those.
  * Score by COMPLETION, never by diagnosis. A trial counts as recovered only when the
    stage reaches `accepted` AND the run yields a gate-passing property value. That is the
    definition round-1's own artifacts failed -- RECOV_F5/F6_AGENT record resolved=true with
    stages_completed=[] -- and it is the reviewer's.

    python3 benchmarks/recovery_r2/fault_catalog.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from code_inventory import inventory  # noqa: E402


@dataclass(frozen=True)
class Fault:
    id: str
    code: str                 #: the Finding.code this must mint -- validated against the registry
    remedy: str               #: the remedy_id the registry routes that code to
    stage: str
    injection: str            #: what is perturbed, precisely enough to implement
    physics: bool             #: True when real MD must run and fail; False = gate-level
    cost: str
    round1: str = ""          #: the round-1 fault this descends from, if any
    notes: str = ""
    implemented: bool = False #: flipped when the injector exists AND has been shown to fire
    caveats: list = field(default_factory=list)


CATALOG = [
    Fault(id="V1", code="BUILD_CELL_INVALID", remedy="agent_only", stage="build",
          injection="Drop rows from the built cell's Atoms section so the header over-counts, "
                    "leaving Bonds/Angles/Dihedrals referencing ids that no longer exist. "
                    "Post-build validation (run_campaign.py:487) mints the code from any "
                    "non-SIZE_ validation error.",
          physics=False, cost="build only, seconds", round1="F6 (data-file corruption)",
          notes="The cheapest route to the agent path. agent_escalations is 0 live across "
                "every v2 run on disk, so {retry, revise_plan, stop} has essentially no "
                "measured behaviour -- this is R3's primary trigger."),
    Fault(id="V2", code="MINIMIZE_NOT_CONVERGED", remedy="raise_minimize_tolerance",
          stage="equilibration",
          injection="Tighten etol/ftol past what the cell can reach in its iteration budget.",
          physics=False, cost="minutes",
          notes="Remedy escalates maxiter/maxeval x4^n and etol/ftol x10^n per attempt, "
                "cap 2 -- so a 3rd failure is designed to exhaust and escalate."),
    Fault(id="V3", code="EXTEND", remedy="continue_npt", stage="equilibration",
          injection="Tighten the equilibration gate's drift/SEM threshold so a healthy melt "
                    "is told to extend.",
          physics=False, cost="one restart-continuation",
          round1="(no round-1 equivalent)",
          notes="EXTEND is the code the gate actually mints. EQUIL_DRIFT / EQUIL_SEM / "
                "EQUIL_N_EFF are routed to the same remedy but have NO producer -- do not "
                "design against them.",
          caveats=["continue_npt sizes its extension from a measured quantity and REFUSES "
                   "rather than guess when none is available (added 2026-09-09 after a "
                   "mis-sized fallback nearly requested a 17,453 ns extension). A fault that "
                   "removes the measurement tests the refusal, not the extension."]),
    Fault(id="V4", code="SIZE_MIN_IMAGE_VIOLATION", remedy="finite_size_rebuild", stage="build",
          injection="Force nchain below the min-image forecast so the built cell self-images.",
          physics=False, cost="build only",
          notes="invalidate_from=build, so a successful remedy rebuilds the cell -- the one "
                "automatic remedy whose success is visible as a different cell, not just a "
                "different parameter."),
    Fault(id="V5", code="TG_REVIEW", remedy="tg_breakpoint", stage="thermal",
          injection="Narrow the sweep window so the bilinear fit's breakpoint is ambiguous.",
          physics=False, cost="thermal replay",
          notes="The remedy halves tg_t_step_K, but ONLY for the breakpoint_ambiguity "
                "sub-cause; it declines method_gap, whose fix (lower tg_rate_K_per_ns) is "
                "agent_only because it invalidates cooling too. Both sub-cases are worth a "
                "trial -- they exercise opposite branches of the same remedy.",
          caveats=["All 21 classes sit at exactly 1.00x tg_min_steps_per_T, so halving "
                   "tg_t_step_K drops the sweep under its own sampling floor and tg_breakpoint "
                   "declines. Measure that: the remedy may be unreachable in practice."]),
    Fault(id="V6", code="BM_INADMISSIBLE_NONMONOTONIC", remedy="murnaghan_resample",
          stage="mechanical",
          injection="Replay an archived non-monotonic pressure series from "
                    "PolyJarvis/data/murnaghan_diagnostics/ rather than generating one.",
          physics=False, cost="~0 (replay)",
          notes="Real cavitation-contaminated series already exist on disk; generating a "
                "fresh one would cost a full ladder for no extra realism."),
]

#: Faults deliberately NOT ported from round 1, with the reason.
NOT_PORTED = {
    "F1 (PPPM out of range)": "no registry code -- a LAMMPS abort mints generic PROCESS_FAILED, "
                              "which transient_retry handles identically to any other crash. "
                              "Nothing specific to measure.",
    "F2 (FF style mismatch)": "same: surfaces as PROCESS_FAILED.",
    "F3 (Tg fit too narrow)": "superseded by V5, which targets the real TG_REVIEW route.",
    "F4 (bad SMILES, 3 stars)": "raises ValueError in mcp-emc-server/smiles_to_emc.py:98 at "
                                "build time; where that surfaces in v2's code vocabulary is "
                                "UNVERIFIED. V1 is the reliable agent_only trigger instead.",
    "error_classifier.py": "its 15 regex rows assert against round-1 recover.md line numbers; "
                           "v2 restructured that file. Scoring keys off Finding.code now.",
}


def validate(catalog=CATALOG) -> list[str]:
    """Refuse a fault the registry cannot route, or whose code nothing mints."""
    inv = inventory()
    live = {**inv["live_automatic"], **inv["live_agent_only"]}
    failures = []
    seen = set()
    for fault in catalog:
        if fault.id in seen:
            failures.append(f"{fault.id}: duplicate id")
        seen.add(fault.id)
        if fault.code in inv["unreachable"]:
            failures.append(f"{fault.id}: {fault.code} is UNREACHABLE "
                            f"({inv['unreachable'][fault.code]['why']}) -- this fault would "
                            f"fire nothing")
        elif fault.code not in live:
            failures.append(f"{fault.id}: {fault.code} is not routed by default_remedies()")
        elif live[fault.code]["remedy_id"] != fault.remedy:
            failures.append(f"{fault.id}: registry routes {fault.code} to "
                            f"{live[fault.code]['remedy_id']!r}, catalog says {fault.remedy!r}")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    failures = validate()
    if args.json:
        print(json.dumps({"catalog": [asdict(f) for f in CATALOG],
                          "not_ported": NOT_PORTED, "failures": failures}, indent=2))
        return 1 if failures else 0
    inv = inventory()
    live = {**inv["live_automatic"], **inv["live_agent_only"]}
    print(f"{len(CATALOG)} faults, all keyed to live codes\n")
    print(f"{'id':4s} {'code':30s} {'remedy':24s} {'stage':13s} {'phys':5s} cost")
    for f in CATALOG:
        print(f"{f.id:4s} {f.code:30s} {f.remedy:24s} {f.stage:13s} "
              f"{'yes' if f.physics else 'gate':5s} {f.cost}")
    print(f"\nagent_only faults (exercise the 2-call cap): "
          f"{[f.id for f in CATALOG if live.get(f.code, {}).get('remedy_id') == 'agent_only']}")
    print(f"implemented: {[f.id for f in CATALOG if f.implemented] or 'none yet'}")
    print(f"\nNOT ported from round 1:")
    for name, why in NOT_PORTED.items():
        print(f"  {name}\n      {why}")
    print(f"\nvalidation: {'FAIL -- ' + '; '.join(failures) if failures else 'PASS'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
