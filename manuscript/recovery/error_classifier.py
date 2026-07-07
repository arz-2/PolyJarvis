#!/usr/bin/env python3
"""
Error classifier for the error-recovery benchmark.

The live PolyJarvis pipeline has no programmatic error classifier — failures are
matched against `.claude/commands/recover.md` by the LLM at runtime. This module
encodes that taxonomy as an ordered regex table so the *benchmark* can decide,
deterministically, whether a given failure has a pre-scripted recovery.

This is the formal pre-scripted / inferred boundary:
  - a log/condition that matches a recover.md row  -> prescripted=True  (Tier 1)
  - anything that does not match                    -> prescripted=False (inferred / Tier 3)

It is intentionally NOT wired into the production servers — it exists only to
score the benchmark, keeping "what the benchmarked system did" unchanged.

Each CATALOG entry mirrors one row of recover.md (line numbers below track the
table at .claude/commands/recover.md). `detect` is "log" for rows whose trigger
appears in the LAMMPS log tail, or "metric" for rows detected from an analysis
result (density drift, Tg fit quality) rather than a log string.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RECOVER_MD = REPO_ROOT / ".claude" / "commands" / "recover.md"

# Ordered: first match wins. Patterns target real LAMMPS/EMC log text.
CATALOG = [
    {
        "error_class": "lost_atoms",
        "detect": "log",
        "pattern": r"lost atoms",
        "recover_md_line": 27,
        "recovery": "Re-spawn worker with dt_fs: 0.5",
    },
    {
        "error_class": "gpu_oom",
        "detect": "log",
        "pattern": r"out of memory|cannot allocate|cudaMalloc|CUDA error:.*memory",
        "recover_md_line": 28,
        "recovery": "Re-spawn with mpi_ranks halved",
    },
    {
        "error_class": "unknown_atom_type",
        "detect": "log",
        "pattern": r"unknown atom type|incorrect atom type|atom type out of range",
        "recover_md_line": 29,
        "recovery": "Re-spawn molecule-builder from assign_forcefield step",
    },
    {
        "error_class": "pppm_out_of_range",
        "detect": "log",
        # LAMMPS: "Out of range atoms - cannot compute PPPM"
        "pattern": r"out of range atoms.*cannot compute pppm|cannot compute pppm",
        "recover_md_line": 39,
        "recovery": "Compress pair_style -> lj/cut/coul/cut; skin=3.0; dt=0.5; restore kspace downstream",
    },
    {
        "error_class": "ff_style_mismatch",
        "detect": "log",
        # wrong style keyword in first steps: fourier / none / lj/charmm / unknown *_style
        "pattern": (
            r"unknown (pair|bond|angle|dihedral|improper)_style"
            r"|illegal .*_style|unrecognized .*style|"
            r"(pair|bond|angle|dihedral) coeffs are not set|"
            r"all pair coeffs are not set|"
            # real LAMMPS runtime crash when class2 coeffs hit the wrong style (captured
            # 2026-06-27): "ERROR: Incorrect args for bond coefficients"
            r"incorrect args for (pair|bond|angle|dihedral|improper) coefficient|"
            # the real ScriptGenerator pre-flight rejection (not a fabricated log):
            r"ff flag mismatch|requires use_(pcff|trappe|opls)"
        ),
        "recover_md_line": 36,
        "recovery": "Re-generate script passing explicit use_trappe/use_pcff/use_opls flag",
    },
    {
        "error_class": "missing_ff_parameters",
        "detect": "log",
        # recover.md row 35 is specifically the SMILES-attachment case (fixable by
        # checking the two * atoms / lowering dp). A genuinely *unsupported* field
        # increment (e.g. PURA pcff missing n_2,hn) has NO scripted fix and must stay
        # inferred — so we deliberately do NOT match "increment not found" here.
        # Real build_cell validator message (captured 2026-06-27):
        # "SMILES must have exactly 2 * connection points, found 3". This is the
        # SMILES-attachment case (fixable). Distinct from F5's EMC field-apply abort,
        # which is handled by the inferred sentinel below — do NOT add a generic
        # "missing force field parameters" here or it would swallow F5.
        "pattern": (r"missing ff parameters|emc build.*missing parameters|"
                    r"exactly 2 \* connection points|exactly two \* connection points|"
                    r"must have exactly .* \* connection"),
        "recover_md_line": 35,
        "recovery": "Verify exactly two * atoms; try dp: 15 if dp: 20 fails",
    },
    {
        "error_class": "energy_nan",
        "detect": "log",
        "pattern": r"\bnan\b|non-numeric|ERROR on proc.*nan",
        "recover_md_line": 30,
        "recovery": "Re-spawn with density_initial - 0.10 g/cm^3",
    },
    {
        "error_class": "external_kill",
        "detect": "log",
        "pattern": r"killed|terminated|process gone|signal (9|15)",
        "recover_md_line": 37,
        "recovery": "Resume remaining stages as a new chain from last *_out.data checkpoint",
    },
    # ---- metric-detected rows (not a log string; surfaced by analysis tools) ----
    {
        "error_class": "density_drift",
        "detect": "metric",
        "pattern": None,
        "recover_md_line": 31,
        "recovery": "Restart compress with density_initial - 0.05 g/cm^3",
    },
    {
        "error_class": "tg_fit_too_narrow",
        # extract_thermal recovery_hint: R2<0.80 or <4 bins. Real failure strings captured
        # 2026-06-27 from extract_thermal on a too-narrow sweep — detect via log so the
        # execute path's genuine extract_thermal output classifies.
        "detect": "log",
        "pattern": (r"bilinear_curvefit failed|"
                    r"need at least 4 .*temperature bins|"
                    r"only \d+ temperature bins? found|"
                    r"check temperature range and data quality"),
        "recover_md_line": 32,
        "recovery": "Re-run sweep: T_start + 50 K, T_end - 50 K",
    },
    {
        "error_class": "tg_fit_borderline",
        "detect": "metric",
        "pattern": None,
        "recover_md_line": 33,
        "recovery": "Re-run sweep with T_step halved",
    },
    {
        "error_class": "radonpy_qm_failed",
        "detect": "metric",
        "pattern": None,
        "recover_md_line": 34,
        "recovery": "Retry with n_conformers halved; else AM1-BCC",
    },
    {
        "error_class": "monitor_hang",
        "detect": "metric",
        "pattern": None,
        "recover_md_line": 38,
        "recovery": "grep STAGE COMPLETE; proceed without Monitor if all stages present",
    },
    {
        "error_class": "bm_wrong_input_data",
        "detect": "metric",  # K<0 or melt-density for a glassy polymer
        "pattern": None,
        "recover_md_line": 40,
        "recovery": "Use npt_prod300_out.data (not npt_production melt data)",
    },
    {
        "error_class": "tg_partial_sweep_bins",
        "detect": "metric",
        "pattern": None,
        "recover_md_line": 41,
        "recovery": "If >=60% T points + both slopes, attempt extract_thermal; else restart sweep",
    },
]

# Inferred sentinels — genuine errors that have NO recover.md row by design. Checked
# BEFORE the prescripted table so a real failure that is textually adjacent to a
# prescripted row (F5's "Missing force field parameters" near F4's row) is never
# misclassified as prescripted. These map to the Tier-3 cases the AGENT must reason
# (F5 reroute-to-RadonPy, F6 rebuild) — captured from real runs 2026-06-27.
INFERRED_PATTERNS = [
    (r"increment pair \{.*\} not found|increment .* not found",
     "emc_unsupported_increment"),          # F5: pcff lacks the increment — reroute builder
    (r"incorrect format in .* section of data file|data file.*incorrect format",
     "data_file_corruption"),               # F6: corrupted topology — rebuild from source
]

# The full set of pre-scripted error classes (membership = prescripted boundary).
PRESCRIPTED_CLASSES = {row["error_class"] for row in CATALOG}

# Sanity: catalog size must match the recover.md table (15 rows).
EXPECTED_ROWS = 15


def classify_error(log_tail: str) -> dict:
    """
    Classify a LAMMPS/EMC log tail against the recover.md taxonomy.

    Returns a dict:
      {error_class, recover_md_line, prescripted: bool, recovery, matched_pattern}
    A match against any log-detectable row => prescripted=True.
    No match => error_class="unknown", prescripted=False (inferred recovery needed).
    """
    text = log_tail or ""
    # Inferred sentinels first: a real error matching one of these is Tier-3 (no scripted
    # fix) even if a prescripted pattern would also match — keeps F5/F6 honestly inferred.
    for pattern, klass in INFERRED_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return {
                "error_class": "unknown",   # inferred boundary: not in PRESCRIPTED_CLASSES
                "recover_md_line": None,
                "prescripted": False,
                "recovery": None,
                "matched_pattern": pattern,
                "inferred_class": klass,    # informational: which Tier-3 case this is
            }
    for row in CATALOG:
        if row["detect"] != "log" or not row["pattern"]:
            continue
        if re.search(row["pattern"], text, re.IGNORECASE):
            return {
                "error_class": row["error_class"],
                "recover_md_line": row["recover_md_line"],
                "prescripted": True,
                "recovery": row["recovery"],
                "matched_pattern": row["pattern"],
            }
    return {
        "error_class": "unknown",
        "recover_md_line": None,
        "prescripted": False,
        "recovery": None,
        "matched_pattern": None,
    }


def is_prescripted(error_class: str) -> bool:
    """True if the error_class corresponds to a recover.md row (Tier 1)."""
    return error_class in PRESCRIPTED_CLASSES


if __name__ == "__main__":
    import json
    import sys

    tail = sys.stdin.read() if not sys.stdin.isatty() else ""
    print(json.dumps(classify_error(tail), indent=2))
