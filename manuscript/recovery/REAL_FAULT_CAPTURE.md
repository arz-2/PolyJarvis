# Real runtime fault capture (--execute design input)

Captured 2026-06-27 by firing each fault's REAL trigger on this machine (tiny runtime-generated
PCFF cells; LAMMPS serial CPU + real EMC + real extract_thermal). These replace the fabricated /
representative strings in fault_catalog.py. Base cell is generated at runtime (build_cell, pcff,
PMMA `*CC(C)(C(=O)OC)*`) for portability — no dependence on the in-repo hardware/CALIB_PCFF cell.

| Fault | Real trigger | Genuine error captured | Class / tier |
|---|---|---|---|
| **F1** pppm_out_of_range | sparse cell (ρ=0.05, dp5×4) + hard NPT compress (P=1e5 atm, dt=4, T=600) | `ERROR on proc 0: Out of range atoms - cannot compute PPPM (src/KSPACE/pppm.cpp:1825)` | prescripted (recover.md:39) |
| **F2** ff_style_mismatch | class2 data+params run with wrong styles (bond_style harmonic, pair lj/cut) | `ERROR: Incorrect args for bond coefficients` | prescripted (recover.md:36) |
| **F3** tg_fit_too_narrow | real short/narrow Tg sweep → real extract_thermal | `status:failed … bilinear_curvefit failed — check temperature range and data quality` (or `Only N temperature bins found — need at least 4` when coverage is truly minimal) | prescripted (recover.md:32) |
| **F4** missing_ff_parameters | real build_cell with 3-star SMILES `*CC*C*` | `SMILES must have exactly 2 * connection points, found 3: '*CC*C*'` (build_cell validator) | prescripted (recover.md:35) — **validator-class, not a runtime crash** |
| **F5** emc_unsupported_increment | real build_cell PURA `*NC(=O)NCCCCCC*` field=pcff | `Warning: increment pair {n_2, hn} not found.` then `Error: …entry.c:645 ScriptFieldEntryApply: Missing force field parameters. Program aborted.` (EMC exit 255) | **INFERRED** (no recover.md row) |
| **F6** data_file_corruption | real LAMMPS read_data on a corrupted .data (Atoms section truncated below header count) | `ERROR: Incorrect format in Atoms section of data file: Bonds … (src/atom.cpp:1201)` | **INFERRED** |

## Recovery verified
- **F1**: switch to `lj/cut/coul/cut` (no kspace) + skin 3.0 + dt 0.5 (recover.md:39) → exit 0, no PPPM error. CONFIRMED resolves.

## Classifier regex drift to fix (error_classifier.py)
The smoke catalog matched fabricated strings; real strings differ. Required updates, preserving the
prescripted/inferred boundary:
- **F2**: add `Incorrect args for (bond|angle|dihedral|improper|pair) coefficients` → ff_style_mismatch (prescripted).
- **F3**: add `bilinear_curvefit failed` / `need at least 4 … temperature bins` → tg_fit_too_narrow (prescripted).
- **F4**: add `exactly 2 \* connection points` / `found \d+` → missing_ff_parameters (prescripted).
- **F5**: add `increment pair \{.*\} not found` → unsupported_increment = **unknown/INFERRED**. MUST be ordered
  BEFORE any generic "Missing force field parameters" rule so F5 is NOT misread as F4's prescripted fix
  (F5's true fix is reroute-to-RadonPy, NOT a SMILES edit). F4's real signal is the star-count message,
  which fires before EMC — so F4 and F5 are textually distinct in practice.
- **F6**: `Incorrect format in .* section of data file` / `atom.cpp` → unknown/INFERRED (no prescripted row).

## Honesty labels (carry into writeup)
- crash faults: F1, F2, F6 (real LAMMPS runtime aborts)
- validator faults: F4 (build_cell pre-flight), F5 (EMC field-apply abort — runtime within EMC)
- metric fault: F3 (analysis-result condition from real extract_thermal)
- "resolved" in the --execute path = re-ran past the failure (F1 confirmed); F5/F6 stay agent-left (recover=None).
