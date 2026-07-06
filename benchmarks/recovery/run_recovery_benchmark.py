#!/usr/bin/env python3
"""
Error-recovery benchmark runner.

Drives the fault catalog: inject each fault, classify the resulting signal, and
(for pre-scripted faults) apply the recover.md fix and verify it resolves. Inferred
faults (generalization probes) have no scripted recovery and are recorded as
"left for AGENT" — the agent resolves those at the full launch, not here.

Reports an overall pre-scripted recovery success rate plus a pre-scripted-vs-inferred
breakdown (incl. attempts/failures).

Usage:
  python benchmarks/recovery/run_recovery_benchmark.py --faults all --smoke
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from error_classifier import classify_error  # noqa: E402
from fault_catalog import CATALOG  # noqa: E402
from metrics import RecoveryEvent, RunMetrics, recovery_success_rate  # noqa: E402


def run_one(fault, tmp: Path) -> dict:
    sig = fault.inject(tmp)

    # Detection / classification.
    if sig.kind == "log":
        cls = classify_error(sig.text)
        classifier_class = cls["error_class"]
        classifier_prescripted = cls["prescripted"]
        classifier_ok = (classifier_class == fault.expected_error_class
                         and classifier_prescripted == fault.prescripted)
    else:
        # metric / reject: detection is the injection firing; labeling comes from the
        # catalog (its recover.md membership), not the log regex.
        classifier_class = fault.expected_error_class
        classifier_prescripted = fault.prescripted
        classifier_ok = sig.triggered

    # Recovery.
    rec = fault.recover(tmp)
    if rec is None:                      # inferred — no scripted recovery
        resolved = False
        recovery_note = "no scripted recovery (inferred — AGENT resolves at launch)"
    else:
        resolved = bool(rec)
        recovery_note = "recover.md fix applied and verified" if resolved else "recovery failed"

    return {
        "id": fault.id,
        "description": fault.description,
        "signal_kind": sig.kind,
        "signal": sig.text,
        "triggered": sig.triggered,
        "expected_error_class": fault.expected_error_class,
        "classifier_error_class": classifier_class,
        "classifier_ok": classifier_ok,
        "prescripted": fault.prescripted,
        "recover_md_line": fault.recover_md_line,
        "recovery_resolved": resolved,
        "recovery_note": recovery_note,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--faults", default="all", help="'all' or comma list of fault ids")
    p.add_argument("--smoke", action="store_true",
                   help="run the cheap injection/recovery surfaces only (no LAMMPS/EMC)")
    p.add_argument("--execute", action="store_true",
                   help="REAL path: launch the actual tool, capture the genuine error, "
                        "recover, and verify (tiny runtime-generated cells). See fault_executors.py")
    p.add_argument("--gpu", type=int, default=None,
                   help="GPU id for --execute LAMMPS decks (default: CPU serial — no contention)")
    args = p.parse_args()

    sel = (None if args.faults == "all"
           else {f.strip() for f in args.faults.split(",")})
    faults = [f for f in CATALOG if sel is None or f.id in sel]

    m = RunMetrics(arm="recovery", system="recovery_benchmark",
                   smoke=(args.smoke and not args.execute)).start()
    per_fault = []
    if args.execute:
        from fault_executors import RealContext, execute_one
        work = Path(tempfile.mkdtemp(prefix="recov_exec_"))
        print(f"# --execute work dir: {work}", file=sys.stderr)
        ctx = RealContext(work_dir=work, gpu_id=args.gpu)
        for fault in faults:
            row = execute_one(fault, ctx)
            per_fault.append(row)
            m.add_recovery(RecoveryEvent(
                fault=row["id"], prescripted=row["prescripted"],
                resolved=row["recovery_resolved"], attempts=1,
                note=row["recovery_note"]))
    else:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            for fault in faults:
                row = run_one(fault, tmp)
                per_fault.append(row)
                m.add_recovery(RecoveryEvent(
                    fault=row["id"], prescripted=row["prescripted"],
                    resolved=row["recovery_resolved"], attempts=1,
                    note=row["recovery_note"]))

    prescripted_events = [e for e in m.recovery_events if e.prescripted]
    inferred_events = [e for e in m.recovery_events if not e.prescripted]
    classifier_failures = [r["id"] for r in per_fault if not r["classifier_ok"]]

    m.terminal_state = "completed"
    m.stop()
    out = m.write()

    summary = {
        "n_faults": len(per_fault),
        "n_prescripted": len(prescripted_events),
        "n_inferred": len(inferred_events),
        "prescripted_recovery_success_rate": recovery_success_rate(prescripted_events),
        "inferred_left_for_agent": [e.fault for e in inferred_events],
        "classifier_failures": classifier_failures,
        "all_triggered": all(r["triggered"] for r in per_fault),
    }
    report = {"summary": summary, "faults": per_fault, "metrics_file": str(out)}
    report_path = (HERE / "results" /
                   f"recovery_benchmark_{'execute' if args.execute else 'smoke'}.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    report["report_file"] = str(report_path)
    print(json.dumps(report, indent=2))

    # Non-zero exit if any injection failed to fire or the classifier mislabeled.
    if classifier_failures or not summary["all_triggered"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
