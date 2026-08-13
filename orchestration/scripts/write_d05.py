#!/usr/bin/env python3
"""
write_d05.py — splice a check_equilibration_comprehensive D-05 block into a run log.

Lets the equil-checker return d05_markdown_path instead of the block itself, keeping the payload
out of the orchestrator's context.

  write_d05.py --run_log data/<RUN>/run_log.md --d05 <d05_block.md>

Replaces the template placeholder under "## D-05 CONVERGENCE DETAIL" on first run, and replaces
the previously written block on re-runs (an EXTEND re-check supersedes its predecessor).
"""
import argparse
import re
import sys
from pathlib import Path

HEADING = "## D-05 CONVERGENCE DETAIL"
PLACEHOLDER = re.compile(
    r"<!-- Paste result\[\"d05_markdown\"\].*?-->", re.S)
MARK_OPEN = "<!-- d05:begin -->"
MARK_CLOSE = "<!-- d05:end -->"
EXISTING = re.compile(re.escape(MARK_OPEN) + r".*?" + re.escape(MARK_CLOSE), re.S)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run_log", required=True)
    p.add_argument("--d05", required=True,
                   help="d05_markdown_path from the check_equilibration_comprehensive result")
    args = p.parse_args()

    run_log = Path(args.run_log)
    block = Path(args.d05).read_text().strip()
    text = run_log.read_text()

    if HEADING not in text:
        print(f"ERROR: '{HEADING}' not found in {run_log}", file=sys.stderr)
        return 1

    wrapped = f"{MARK_OPEN}\n{block}\n{MARK_CLOSE}"
    if EXISTING.search(text):
        text = EXISTING.sub(lambda _: wrapped, text, count=1)
    elif PLACEHOLDER.search(text):
        text = PLACEHOLDER.sub(lambda _: wrapped, text, count=1)
    else:
        head, sep, tail = text.partition(HEADING)
        text = head + sep + "\n\n" + wrapped + tail

    run_log.write_text(text)
    print(f"D-05 written to {run_log}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
