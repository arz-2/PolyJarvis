"""CLI for runlog_miner.

Usage:
    python -m tools.runlog_miner [--data-dir data] [--glob '*/run_log.md']
                                 [--json | --suggest | --diff | --playbook | --calibrate]
                                 [--rules guides/polymer_rules.json]
                                 [--min-support 2] [-o OUTPUT]
"""
from __future__ import annotations

import argparse
import json
import sys

from .parse import load_corpus
from .report import summarize
from .suggest import build_suggestions
from .cluster import build_playbook
from .calibrate import build_calibration


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.runlog_miner",
        description="Parse the PolyJarvis run_log corpus and emit a read-only summary (P0a).",
    )
    ap.add_argument("--data-dir", default="data", help="root dir holding data/[RUN]/run_log.md (default: data)")
    ap.add_argument("--glob", default="*/run_log.md", help="glob under --data-dir (default: */run_log.md)")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--json", action="store_true", help="emit JSON RunRecords")
    mode.add_argument("--suggest", action="store_true", help="emit proposed polymer_rules changes (P0b, advisory)")
    mode.add_argument("--diff", action="store_true", help="emit a unified diff of the numeric suggestions (not applied)")
    mode.add_argument("--playbook", action="store_true", help="emit the recovery playbook markdown (P0c)")
    mode.add_argument("--calibrate", action="store_true", help="emit the confidence-calibration report (P0c)")
    ap.add_argument("--rules", default="guides/polymer_rules.json", help="polymer_rules.json path (for --suggest/--diff/--calibrate)")
    ap.add_argument("--min-support", type=int, default=2, help="min distinct runs agreeing before a change is suggested (default: 2)")
    ap.add_argument("-o", "--output", help="write to this file instead of stdout")
    args = ap.parse_args(argv)

    records = load_corpus(args.data_dir, args.glob)
    if args.json:
        out = json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=False)
    elif args.suggest or args.diff:
        suggestions, diff = build_suggestions(records, args.rules, args.min_support)
        if args.diff:
            out = diff or "# no numeric suggestions (insufficient support or no change)\n"
        else:
            out = json.dumps(suggestions, indent=2, ensure_ascii=False)
    elif args.playbook:
        out = build_playbook(records)
    elif args.calibrate:
        with open(args.rules, encoding="utf-8") as fh:
            rules = json.load(fh)
        out = build_calibration(records, rules)
    else:
        out = summarize(records)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out if out.endswith("\n") else out + "\n")
    else:
        sys.stdout.write(out if out.endswith("\n") else out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
