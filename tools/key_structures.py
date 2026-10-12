#!/usr/bin/env python3
"""List the structure files (LAMMPS .data) that every reported number descends from.

Trajectories and intermediate cells stay out of the repository. Per run workspace:
  build          work/cell/cell.data
  equilibration  the melt-hold output cooling and thermal start from (npt_melt_hold_out.data)
  cooling        the 300 K cell density and the bulk-modulus series start from (npt_final_out.data)
  mechanical     one output per bulk-modulus pressure point (bm_P*_out.data)
The accepted attempt of each stage is used; a stage that ended the run without an accepted attempt
contributes its last attempt, so a terminated run still ships the cell it failed on.

Paths are printed relative to the repository root, one per line, for
`git add -f --pathspec-from-file=-`. Works on either host: absolute paths stored in the run's JSON
are never used.

Usage: python3 tools/key_structures.py data/PE_1 data/PE_2 ... | git add -f --pathspec-from-file=-
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PATTERNS = {
    "build": ["work/cell/cell.data"],
    "equilibration": ["work/npt_melt_hold/npt_melt_hold_out.data"],
    "cooling": ["work/npt_final/npt_final_out.data"],
    "mechanical": ["work/bm_series/p_*/attempt_*/bm_P*/bm_P*_out.data"],
}


def stage_attempt(record: dict) -> str | None:
    if record.get("accepted_attempt"):
        return record["accepted_attempt"]
    attempts = record.get("attempts") or []
    if record.get("status") in ("escalation_required", "failed") and attempts:
        return attempts[-1].get("attempt_id")
    return None


def key_structures(run_dir: Path) -> list[Path]:
    state = json.loads((run_dir / "workflow_state.json").read_text())
    found = []
    for stage, patterns in PATTERNS.items():
        attempt = stage_attempt(state.get("stages", {}).get(stage, {}))
        if not attempt:
            continue
        for pattern in patterns:
            found += sorted((run_dir / "attempts" / stage / attempt).glob(pattern))
    return found


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__, file=sys.stderr)
        return 2
    missing = 0
    for arg in argv:
        run_dir = (REPO / arg).resolve() if not Path(arg).is_absolute() else Path(arg)
        paths = key_structures(run_dir)
        if not paths:
            print(f"no structures found in {arg}", file=sys.stderr)
            missing += 1
        for path in paths:
            print(path.relative_to(REPO))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
