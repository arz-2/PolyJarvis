# bm_diagnostics_r2 — bulk-modulus controlled diagnostics on a current-protocol cell

Redoes `~/PolyJarvis/data/murnaghan_diagnostics` (round-1 PVC3, built and equilibrated with the
retired round-1 protocol) on **sPVC_3**, an accepted round-2 replicate equilibrated with the locked
protocol. Answers reviewer comment 5 (sensitivity to pressure-ladder span, barostat settings,
production length) and settles whether sPVC's −1000 atm point, which the fit script excludes in all
three sPVC replicates, is cavitating or merely under-relaxed.

## Cell and settings (identical to sPVC_3's production mechanical stage)
- Start: `data/sPVC_3/attempts/cooling/attempt-0001/work/npt_final/npt_final_out.data`, copied to
  `data/bm_diagnostics_r2/input/sPVC_3_npt_final_out.data` (sha256 `25c0b6f3…e862`, matches the
  cooling manifest). sPVC_3 itself is read-only.
- Deck: production `run_bulk_modulus_series` → `generate_script("npt")`; regenerated −1000 atm deck is
  byte-identical to sPVC_3's production deck. PCFF `lj/class2/coul/long 9.5`, PPPM 1e-6, SHAKE on H,
  `fix npt temp 300 300 100 iso P P 1000`, 1 fs, thermo 100, velocities read from the data file,
  KOKKOS mpi=1, one pressure per chain.
- Fit: `extract_bulk_modulus_murnaghan.py` defaults (eq_fraction 0.5, window selection and point
  exclusion as in production).

## Legs
| Leg | Knob | Pressures (atm) | New points | Round-1 counterpart |
|---|---|---|---|---|
| baseline | sPVC_3 production (reused logs) | −1000, 0, 1500, 3000, 5000 | 0 | PVC3 archived chain |
| pdamp_250 | barostat damping 250 fs | baseline | 5 | pdamp_250 |
| pdamp_4000 | barostat damping 4000 fs | baseline | 5 | pdamp_4000 |
| nptsteps_250k | 250k steps (first 250k steps of baseline logs) | baseline | 0 | nptsteps_250k |
| nptsteps_1M | 1M steps | baseline | 5 | nptsteps_1M |
| span_check | ±1000 atm span | −1000, −500, 0, 500, 1000 | 3 | span_check |
| points_7 | 7-point ladder | −1000, 0, 750, 1500, 3000, 4000, 5000 | 2 | points_7 |
| wide_compression | 15000 atm ceiling | −1000, 0, 3000, 7000, 15000 | 2 | wide_compression |
| no_tension | no tension point | 1, 1250, 2500, 3750, 5000 | 4 | no_tension |
| no_tension_prod | baseline minus −1000 (production fit window) | 0, 1500, 3000, 5000 | 0 | — |
| tension_series | tension resolution | −1000, −500, −250, 0 (+ −1000 at 1M steps from nptsteps_1M) | 1 (−250; −500 shared) | new |

27 distinct new points ≈ 13.3 GPU-h (sPVC_3 production: 1491 s per 500k-step point).
System size is not repeated here (round-1 used a rubbery PEG pair; a glassy size test is separate).

## Files
- `legs.py` — leg/point registry (`python3 legs.py` lists it)
- `run_legs.py` — resumable launcher, one GPU claim (run name `bm_diagnostics_r2`), dumps gzipped
- `analyze.py` — fits all legs, writes `results/results.json` and the table below
- `status.json`, `launcher.log`, `launcher.pid` — launcher state
- Simulations: `data/bm_diagnostics_r2/points/<P>_damp<d>_steps<n>/bm_P<P>/`

## Run
```
setsid nohup mcp-servers/.venv/bin/python benchmarks/bm_diagnostics_r2/run_legs.py \
    >> benchmarks/bm_diagnostics_r2/launcher.log 2>&1 &
mcp-servers/.venv/bin/python benchmarks/bm_diagnostics_r2/analyze.py   # any time; incomplete legs show pending
```

## Results
<!-- RESULTS:START -->
_Generated 2026-09-15T16:01:24.641105+00:00 by analyze.py._

| Leg | Axis | Pressures fitted (atm) | B0 (GPa) | ΔB0 vs baseline | B0′ | R² | Excluded | All-points B0 (GPa) | Gate |
|---|---|---|---|---|---|---|---|---|---|
| baseline | sPVC_3 production series (reused) | 0, 1500, 3000, 5000 | 3.759 | +0.0% | 6.39 | 0.99964 | -1000 | 2.888 | BM_REPORTABLE |
| pdamp_250 | barostat damping 250 fs | -1000, 0, 1500, 3000, 5000 | 2.770 | -26.3% | 10.91 | 0.99768 | — | 2.770 | BM_REPORTABLE |
| pdamp_4000 | barostat damping 4000 fs | -1000, 0, 1500, 3000 | 2.886 | -23.2% | 13.00 | 0.99995 | 5000 | 2.957 | BM_REPORTABLE |
| nptsteps_250k | production 250k steps (first half of baseline logs) | -1000, 0, 1500, 3000, 5000 | 3.057 | -18.7% | 9.28 | 0.99949 | — | 3.057 | BM_REPORTABLE |
| nptsteps_1M | production 1M steps | -1000, 0, 1500, 3000, 5000 | 2.797 | -25.6% | 9.46 | 0.99954 | — | 2.797 | BM_REPORTABLE |
| span_check | ladder span +/-1000 atm | -1000, -500, 0, 500, 1000 | 2.963 | -21.2% | 18.03 | 0.99984 | — | 2.963 | BM_REPORTABLE |
| points_7 | 7-point ladder | 750, 1500, 3000, 4000, 5000 | 4.361 | +16.0% | 4.76 | 0.99851 | -1000, 0 | 2.900 | BM_INADMISSIBLE |
| wide_compression | 15000 atm ceiling | -1000, 0, 3000, 7000, 15000 | 3.024 | -19.6% | 8.16 | 0.99958 | — | 3.024 | BM_REPORTABLE |
| no_tension | no tension point (round-1 ladder 1-5000 atm) | 1, 1250, 2500, 3750, 5000 | 3.180 | -15.4% | 9.27 | 0.99995 | — | 3.180 | BM_REPORTABLE |
| no_tension_prod | baseline without -1000 atm (production fit window) | 0, 1500, 3000, 5000 | 3.759 | +0.0% | 6.39 | 0.99964 | — | 3.759 | BM_REPORTABLE |
| tension_series | tension resolution -1000..0 atm | -1000, -500, -250, 0 | 2.694 | -28.3% | 13.26 | 0.99652 | — | 2.694 | BM_REPORTABLE |

Tension diagnostics (production window = last 50% of each log):

| P (atm) | steps | ⟨V⟩ (Å³) | σV | τ (frames) | n_eff | second−first half ⟨V⟩ (σ) | range/σ |
|---|---|---|---|---|---|---|---|
| -1000 | 500000 | 66514.9 | 436.3 | 126.8 | 19 | 0.29 | 6.35 |
| -500 | 500000 | 64421.7 | 378.5 | 294.63 | 8 | 0.93 | 7.64 |
| -250 | 500000 | 63854.6 | 316.0 | 5.57 | 448 | 0.15 | 6.64 |
| 0 | 500000 | 63102.0 | 277.0 | 4.58 | 546 | -0.34 | 6.28 |
| -1000 | 1000000 | 66355.1 | 410.5 | 187.34 | 26 | 0.48 | 7.09 |

Baseline reproduces stored sPVC_3 B0 (3.7592 GPa): True
<!-- RESULTS:END -->
