# cross_grade — PEG1 under both codes' convergence criteria

RadonPy's stock run on PEG1 never reached `check_eq`; neither did nine further 9-hour
equilibrations (`preserved_artifacts/PEG1_retry9`). PolyJarvis cells of the same SMILES pass
their own gate. Before that contrast can be quoted, one question has to be answered: **did
PolyJarvis converge PEG, or does it just call a different state converged?** Every cell here is
graded by both codes.

    mcp-servers/.venv/bin/python benchmarks/polyjarvis_vs_radonpy/cross_grade/run_cross_grade.py
        [--only PEGCMP1,radonpy_retry9] [--reuse-checker]
    mcp-servers/.venv/bin/python -m pytest benchmarks/polyjarvis_vs_radonpy/tests/test_cross_grade.py

CPU only. It reads the 1–2 GB production dumps in place and writes a few MB of results under
`results/PEG1/`. `arms.json` defines the cells and windows.

## The grid

| | RadonPy's `check_eq` criteria | PolyJarvis's gate (`require_rubbery`) |
|---|---|---|
| **RadonPy cells** (`eq3.log` stock, `eq12.log` retry 9) | its own verdict, reproduced from the log | thermo + recovered Rg CV + finite size; homogeneity unmeasured |
| **PolyJarvis cells** (PEGCMP1, PEGORE1, 2X size checks) | `rg.profile` rebuilt from the dump; every criterion | the real checker on the real dump |

**Why these PolyJarvis cells, not "PEG1".** No v2 PolyJarvis PEG1 run exists, and round-1
`manuscript/data/PEG1` kept no trajectory (44 MB total), so it can carry only half a grade.
PEGCMP1 and PEGORE1 are the same SMILES, 10 chains, 300 K, full 2 ns NPT dumps, and a
single-line controlled force-field pair (COMPASS vs pcff_ore). The 20-chain runs are size
checks. RadonPy's cell is GAFF2_mod with RESP charges — so this grades **convergence
definitions**, not force-field accuracy.

## Every number is the owning code's

- **RadonPy side** — `Equilibration_analyze`, `analyze_thermo` (with `get_all_prop`'s unit
  conversions) and `calc_rg`, with thresholds read off the analyzer's `*_crit` attributes. Run
  inside the `radonpy` env. On RadonPy's own logs the grader must reproduce RadonPy's stored
  `eq_conv_data.csv` sma_sd for every term or the run aborts; it does, exactly, on both.
- **PolyJarvis side** — `check_equilibration_comprehensive.py` as a subprocess, then
  `enforce_gate.collect_gates` and `enforce_gate.classify`. Log-only cells use the checker's
  own `check_thermo`.
- **`rg.profile`** — per-chain mass-weighted Rg on image-unwrapped coordinates (what
  `compute gyration/chunk` reports), written in `fix ave/time mode vector` layout. The driver
  aborts unless RadonPy's parser reads back the same `sd_max` numpy computed on the matrix.

## Two windows

- **native** — RadonPy's default, width 2000 on the full log. RadonPy logs hold 5001 rows;
  PolyJarvis production logs hold 2001, where every sma_sd is undefined.
- **matched** — both arms cut to their last 2001 rows (2 ns), width 800: the same 40% of the
  window RadonPy's 2000/5001 uses. A shorter rolling mean fluctuates more, so matched is
  stricter than native, **on both arms equally**. The matched verdict is the comparison;
  native is reported for provenance.

## Reading rule — fixed before any PolyJarvis cell was graded

1. "PolyJarvis converged PEG where RadonPy did not" is licensed **only if** the PolyJarvis cells
   PASS RadonPy's criteria at the matched window, Rg included.
2. If they FAIL RadonPy's Rg or energy criteria, the finding is that **the definitions differ**:
   RadonPy's is stricter on that axis, and what distinguishes the codes is the response to a
   failing criterion — RadonPy repeated the same run nine times — not convergence.
3. INCOMPLETE is never read as PASS on either side.

## Found while building it — RadonPy fails open twice

Both are the shape PolyJarvis's own melt gate had until 2026-09-09.

- **Short window.** `analyze_thermo` returns NaN when rows < 2×width, and `check_eq` compares
  with `>`, so every NaN criterion passes. On a 2001-row PolyJarvis log at default width,
  `check_eq` returns True with nothing computed. Here that is UNEVALUABLE.
- **Missing Rg profile.** With no readable `rg.profile`, `check_eq` prints "Skip to check the Rg
  convergence" and returns True. On both preserved RadonPy logs — the runs RadonPy itself
  rejected on Rg — `check_eq` now returns True. `radonpy_check_eq_skipped_rg` records it.

## Biases and caveats, stated rather than corrected

- **Snapshot vs averaged Rg.** RadonPy's profile holds 1000-step running averages; a dump holds
  instantaneous snapshots. This inflates per-chain sd, so it can only make a PolyJarvis cell
  look *less* converged under RadonPy's rule.
- **Relative energy criteria depend on the force field's energy zero.** `TotEng` averages
  ~148 000 kJ/mol for GAFF2_mod and ~36 000 for COMPASS, so `sma_sd > |mean|×crit` is about
  4× tighter on the PolyJarvis cells for the same fluctuation. Report the sma_sd values, not
  just the verdict.
- **Protocol differences:**
  - cutoff 12.0 Å (RadonPy) vs 9.5 Å (PolyJarvis);
  - SHAKE on RadonPy only;
  - 10 020 vs 7 020 / 14 040 atoms.
- **RadonPy cells are graded without a trajectory.** Their dump, xtc and `rg.profile` were not
  preserved, so for them:
  - PolyJarvis's `density_homogeneity`, `p2`, `torsion` and `chain_displacement` are
    unmeasured;
  - RadonPy's Rg is only available at the native window, from its stored CSV.
- **Autocorrelation correction.** PolyJarvis's per-term drift uses the autocorrelation-corrected
  p-value added 2026-09-10. `component_drift_failing_under_naive_p` shows what the gate said
  before that; RadonPy retry 9's dihedral (1.48% drift) is one such term.

## Not done

Grading the RadonPy cell with PolyJarvis's trajectory gates needs RadonPy's stock run repeated
with its trajectory kept. That is roughly 13 GPU-h (eq1 15 min, eq2 3.8 h, eq3 9 h) and ~5 GB
of dump. It has not been launched.
