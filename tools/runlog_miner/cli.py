"""CLI for runlog_miner P0a.

Usage:
    python -m tools.runlog_miner [--data-dir data] [--glob '*/run_log.md']
                                 [--json] [-o OUTPUT]
"""
from __future__ import annotations

import argparse
import json
import sys

from .parse import load_corpus
from .report import summarize


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m tools.runlog_miner",
        description="Parse the PolyJarvis run_log corpus and emit a read-only summary (P0a).",
    )
    ap.add_argument("--data-dir", default="data", help="root dir holding data/[RUN]/run_log.md (default: data)")
    ap.add_argument("--glob", default="*/run_log.md", help="glob under --data-dir (default: */run_log.md)")
    ap.add_argument("--json", action="store_true", help="emit JSON RunRecords instead of the markdown report")
    ap.add_argument("-o", "--output", help="write to this file instead of stdout")
    args = ap.parse_args(argv)

    records = load_corpus(args.data_dir, args.glob)
    out = (
        json.dumps([r.to_dict() for r in records], indent=2, ensure_ascii=False)
        if args.json
        else summarize(records)
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as fh:
            fh.write(out if out.endswith("\n") else out + "\n")
    else:
        sys.stdout.write(out if out.endswith("\n") else out + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
