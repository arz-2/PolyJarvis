#!/usr/bin/env python3
"""
REVISION-TEMP: update_revision_progress.py
-----------------------------------------------
Scans simulation directories and updates the Revision Progress table in
guides/REVISION_PARAMS.md. Hook-triggered during ACS manuscript revision runs.

Remove this script and its hooks in .claude/settings.json after ACS resubmission.
Added: 2026-06-04
"""

import os
import re
from pathlib import Path

DATA_DIR    = Path("/home/alexzhao/PolyJarvis/data")
SIM_DIR     = Path("/home/alexzhao/simulations")
PARAMS_FILE = Path("/home/alexzhao/PolyJarvis/guides/REVISION_PARAMS.md")

# Per polymer: regex to match run dirs, which dirs to scan, and how many reps are needed.
# PE scans DATA_DIR only — old PE_run1-3 (10 chains) are deprecated for the revision.
# PEG/PMMA/PS scan both: existing 3 legacy runs in SIM_DIR are valid, new reps 4-5 go in DATA_DIR.
# NYLON6/BPAPC/PVDF/PDMS scan DATA_DIR only (all-new revision runs).
POLYMER_CONFIG = {
    "PE":      {"regex": r"^PE[\d_]",    "dirs": [DATA_DIR],          "target": 5},
    "PEG":     {"regex": r"^PEG[\d_]",   "dirs": [DATA_DIR, SIM_DIR], "target": 5},
    "PMMA":    {"regex": r"^PMMA[\d_]",  "dirs": [DATA_DIR, SIM_DIR], "target": 5},
    "PS":      {"regex": r"^PS[\d_]",    "dirs": [DATA_DIR, SIM_DIR], "target": 5},
    "Nylon-6": {"regex": r"^NYLON6",     "dirs": [DATA_DIR],          "target": 5},
    "BPA-PC":  {"regex": r"^BPAPC",      "dirs": [DATA_DIR],          "target": 5},
    "PVDF":    {"regex": r"^PVDF",       "dirs": [DATA_DIR],          "target": 5},
    "PDMS":    {"regex": r"^PDMS",       "dirs": [DATA_DIR],          "target": 5},
}


def stage_of(run_dir: Path) -> int:
    """Highest stage completed: 0=none, 1=build, 2=equil, 3=tg, 4=analysis."""
    if not run_dir.is_dir():
        return 0
    # S4: analysis directory present
    if (run_dir / "analysis").is_dir():
        return 4
    # S3: any tg_sweep* directory
    if any(run_dir.glob("tg_sweep*")):
        return 3
    # S2: equilibration output directory
    equil_dirs = ("eq", "equil", "06_nvt_production")
    if any((run_dir / d).is_dir() for d in equil_dirs):
        return 2
    # S1: LAMMPS .data file or mol/ directory from molecule builder
    if list(run_dir.glob("*.data")) or (run_dir / "cell.data").exists() or (run_dir / "mol").is_dir():
        return 1
    return 0


def count_stages(config: dict) -> dict:
    """Count reps that have completed each stage (or further)."""
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    pattern = re.compile(config["regex"], re.IGNORECASE)
    seen = set()
    for search_dir in config["dirs"]:
        if not search_dir.is_dir():
            continue
        for entry in search_dir.iterdir():
            if not entry.is_dir() or entry.name in seen:
                continue
            if pattern.match(entry.name):
                seen.add(entry.name)
                s = stage_of(entry)
                for stage in range(1, s + 1):
                    counts[stage] += 1
    return counts


def fmt(n: int) -> str:
    return "⬜" if n == 0 else f"✅ {n}"


def make_row(polymer: str, counts: dict, target: int) -> str:
    done = counts[4]
    return (
        f"| {polymer} "
        f"| {fmt(counts[1])} "
        f"| {fmt(counts[2])} "
        f"| {fmt(counts[3])} "
        f"| {fmt(counts[4])} "
        f"| {done} / {target} |"
    )


def main():
    text = PARAMS_FILE.read_text()

    rows = [
        make_row(polymer, count_stages(cfg), cfg["target"])
        for polymer, cfg in POLYMER_CONFIG.items()
    ]
    new_body = "\n".join(rows)

    # Replace data rows: from the separator row through to the PE footnote.
    # Group 1 = separator row, group 2 = data rows, group 3 = blank line + footnote.
    pattern = re.compile(
        r"(\|[-:| ]+\n)((?:\|[^\n]*\n)+)(\n> \*\*PE:)"
    )
    new_text, n = re.subn(pattern, lambda m: m.group(1) + new_body + "\n" + m.group(3), text)

    if n == 0:
        print("[update_revision_progress] WARNING: progress table not found — skipping update")
        return

    PARAMS_FILE.write_text(new_text)
    print("[update_revision_progress] Progress table updated")


if __name__ == "__main__":
    main()
