#!/usr/bin/env python3
"""
Arm-3 (AGENT) RunMetrics adapter — R1M1 / M7.

Parses a real PolyJarvis orchestrator run (run_log.md + run_summary.json) into the
SAME RunMetrics schema the scripted arms emit (metrics.py), so the 3-arm ablation
table is apples-to-apples.

NOT an independent grader: the run_log RECOVERIES are written by the LLM being graded,
so this reformats self-reported data. It is defensible only because the extraction
rules are fixed a priori (below) — the agent cannot redefine what counts. Say so in
the writeup; do not claim independence.

Extraction rules (fixed a priori):
  wall_clock_s   sum of the SIMULATION STATE "Wall" column over DONE stages
                 (foundation-only → equil/build rows only). Same sim-bound span the
                 scripted arms measure; LLM/orchestration latency is NOT included
                 (recorded separately in notes if known).
  interventions  count of "UNRESOLVED" markers + critic "escalate" in the header.
                 A clean autonomous run = 0 (matches the scripted baseline).
  recovery_events one per RECOVERIES block. Preferred source: a machine-readable tag
                 <!-- RECOVERY: error_class=.. prescripted=.. outcome=.. attempts=.. -->
                 (adopt in new agent runs). Fallback: prose '### R-..' blocks, with
                 resolved := no negative-outcome keyword present, prescripted via
                 error_classifier.classify_error (same Tier-1/Tier-3 rule as the fault
                 benchmark).
  terminal_state stalled if any UNRESOLVED / failed stage; else completed if a
                 run_summary.json exists; else completed_foundation if equil is done.

Usage:
  python benchmarks/autonomy/agent_metrics.py --run_dir data/PMMA2 --system PMMA \
      --polymer_class PACR --seed 734812            # writes results/PMMA_agent.json
  # supplementary accuracy (kept OUT of RunMetrics by design):
  python benchmarks/autonomy/agent_metrics.py --run_dir data/PMMA2 --system PMMA \
      --polymer_class PACR --accuracy --exp_min 1.17 --exp_max 1.188
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from error_classifier import classify_error      # noqa: E402
from metrics import RecoveryEvent, RunMetrics     # noqa: E402

_NEG_OUTCOME = ("unresolved", "escalat", "failed again", "gave up", "abort")
_WALL_RE = re.compile(r"~?\s*(\d+(?:\.\d+)?)\s*h", re.I)
_TAG_RE = re.compile(r"<!--\s*RECOVERY:\s*(.*?)\s*-->", re.S)
_ATTEMPT_RE = re.compile(r"resubmit|re-?run|re-?launch|re-?spawn|attempt|extension", re.I)


def _read_log(run_dir: Path) -> str:
    rl = run_dir / "run_log.md"
    return rl.read_text() if rl.exists() else ""


def _section(text: str, header: str) -> str:
    """Body between '## <header>' and the next '## ' (or EOF)."""
    m = re.search(rf"^##\s+{re.escape(header)}\s*$(.*?)(?=^##\s|\Z)",
                  text, re.M | re.S)
    return m.group(1) if m else ""


def _parse_recoveries(text: str) -> list:
    sec = _section(text, "RECOVERIES")
    if not sec.strip() or re.match(r"^\s*None\s*$", sec.strip(), re.I):
        return []
    events = []
    # Preferred: machine-readable tags (new agent runs).
    tags = _TAG_RE.findall(sec)
    if tags:
        for t in tags:
            kv = dict(re.findall(r"(\w+)\s*=\s*([^\s]+)", t))
            outcome = kv.get("outcome", "").lower()
            events.append(RecoveryEvent(
                fault=kv.get("error_class", "unknown"),
                prescripted=kv.get("prescripted", "false").lower() == "true",
                resolved=not any(n in outcome for n in _NEG_OUTCOME),
                attempts=int(kv.get("attempts", 1)),
                note="from RECOVERY tag"))
        return events
    # Fallback: prose '### R-..' blocks.
    blocks = re.split(r"^###\s+", sec, flags=re.M)[1:]
    for b in blocks:
        low = b.lower()
        cls = classify_error(b)
        events.append(RecoveryEvent(
            fault=cls["error_class"],
            prescripted=cls["prescripted"],
            resolved=not any(n in low for n in _NEG_OUTCOME),
            attempts=len(_ATTEMPT_RE.findall(b)) or 1,
            note=b.splitlines()[0].strip()[:80] if b.strip() else ""))
    return events


def _sim_rows(text: str) -> list:
    sec = _section(text, "SIMULATION STATE")
    rows = []
    for line in sec.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cols = [c.strip() for c in s.strip("|").split("|")]
        if len(cols) < 6:
            continue
        if cols[0].lower() == "stage" or set(cols[0]) <= set("-: "):
            continue
        rows.append(cols)            # Stage, ID, Submitted, Completed, Wall, Status, [notes]
    return rows


def _is_done(row: list) -> bool:
    return "done" in row[5].lower()


def _stage_key(stage: str) -> Optional[str]:
    s = stage.lower()
    if "build" in s:
        return "build"
    if "tg" in s:
        return "tg"
    if any(k in s for k in ("bm_series", "murnaghan", "born", "deform", "bulk")):
        return "bulk_modulus"
    if "equil" in s:
        return "equil"
    return None


def _wall_seconds(rows: list, foundation_only: bool) -> float:
    total_h = 0.0
    for r in rows:
        if not _is_done(r):
            continue
        if foundation_only and _stage_key(r[0]) not in ("build", "equil"):
            continue
        m = _WALL_RE.search(r[4])
        if m:
            total_h += float(m.group(1))
    return round(total_h * 3600.0, 1)


def metrics_from_run(run_dir, system: str, polymer_class: str = "",
                     seed: Optional[int] = None, arm: str = "agent",
                     foundation_only: bool = False) -> RunMetrics:
    run_dir = Path(run_dir)
    text = _read_log(run_dir)
    rows = _sim_rows(text)

    recoveries = _parse_recoveries(text)
    interventions = len(re.findall(r"unresolved", text, re.I))
    header = text.splitlines()[3] if len(text.splitlines()) > 3 else ""
    if re.search(r"critic:[^|]*escalat", header, re.I):
        interventions += 1

    done_keys = []
    for r in rows:
        if _is_done(r):
            k = _stage_key(r[0])
            if k and k not in done_keys:
                done_keys.append(k)
    equil_done = "equil" in done_keys
    if equil_done:
        stages_completed = ["build", "equil", "equil-check"] + \
            [k for k in done_keys if k not in ("build", "equil")]
    else:
        stages_completed = done_keys

    has_summary = (run_dir / "raw" / "run_summary.json").exists()
    stalled = bool(re.search(r"unresolved", text, re.I)) or \
        any("fail" in r[5].lower() and "done" not in r[5].lower() for r in rows)
    if stalled:
        terminal_state = "stalled"
    elif has_summary:
        terminal_state = "completed"
    elif equil_done:
        terminal_state = "completed_foundation"
    else:
        terminal_state = "unknown"

    m = RunMetrics(arm=arm, system=system, polymer_class=polymer_class, seed=seed)
    m.wall_clock_s = _wall_seconds(rows, foundation_only)
    m.interventions = interventions
    m.terminal_state = terminal_state
    m.recovery_events = recoveries
    m.stages_completed = stages_completed
    m.notes = ("parsed from run_log.md (self-reported; rules fixed a priori); "
               "wall_clock_s is sim-bound and excludes LLM latency"
               + ("; foundation-only" if foundation_only else ""))
    return m


def _density_from_run(run_dir: Path):
    """Best-effort 300 K density read for the supplementary accuracy file."""
    summ = run_dir / "raw" / "run_summary.json"
    if summ.exists():
        d = json.load(open(summ)).get("results", {}).get("density", {})
        v = d.get("value_g_cm3") or d.get("value_gcm3")
        if v is not None:
            return float(v), d.get("exp_range_g_cm3"), d.get("error_pct")
    eq = run_dir / "raw" / "equilibrated_density.json"
    if eq.exists():
        d = json.load(open(eq))
        v = d.get("density_gcm3") or d.get("density_g_cm3") or d.get("value_g_cm3")
        if v is not None:
            return float(v), None, None
    return None, None, None


def accuracy_vs_exp(run_dir, exp_min: Optional[float] = None,
                    exp_max: Optional[float] = None) -> dict:
    """Supplementary accuracy read — kept OUT of RunMetrics by design
    (metrics.py: process metrics only, never accuracy)."""
    run_dir = Path(run_dir)
    dens, exp_range, err = _density_from_run(run_dir)
    if exp_min is None and exp_range:
        exp_min, exp_max = exp_range[0], exp_range[1]
    if err is None and dens is not None and exp_min is not None and exp_max is not None:
        mid = 0.5 * (exp_min + exp_max)
        # nearest-bound error (per feedback_glassy_k_routing: not midpoint)
        if dens < exp_min:
            err = round(100.0 * (dens - exp_min) / exp_min, 2)
        elif dens > exp_max:
            err = round(100.0 * (dens - exp_max) / exp_max, 2)
        else:
            err = 0.0
    return {"density_gcm3": dens, "exp_min": exp_min, "exp_max": exp_max,
            "error_pct": err}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--run_dir", required=True)
    p.add_argument("--system", required=True)
    p.add_argument("--polymer_class", default="")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--arm", default="agent")
    p.add_argument("--foundation-only", dest="foundation_only", action="store_true")
    p.add_argument("--accuracy", action="store_true",
                   help="also write the supplementary accuracy JSON")
    p.add_argument("--exp_min", type=float, default=None)
    p.add_argument("--exp_max", type=float, default=None)
    args = p.parse_args()

    m = metrics_from_run(args.run_dir, args.system, args.polymer_class,
                         args.seed, args.arm, args.foundation_only)
    path = m.write()
    print(json.dumps(m.to_dict(), indent=2))
    print(f"\nmetrics -> {path}")

    if args.accuracy:
        acc = accuracy_vs_exp(args.run_dir, args.exp_min, args.exp_max)
        acc_path = path.parent / f"{args.system}_{args.arm}_accuracy.json"
        acc_path.write_text(json.dumps(acc, indent=2))
        print(f"accuracy -> {acc_path}: {acc}")


if __name__ == "__main__":
    main()
