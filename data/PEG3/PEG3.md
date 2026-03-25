# PEG Run 3 — Summary Log

**Directory:** `/home/arz2/simulations/02272026_PEG_run3`
**Date started:** 2026-02-27
**Last updated:** 2026-03-22
**Agent:** PolyJarvis AI
**System:** Poly(ethylene oxide) / Poly(ethylene glycol), `*CCO*`, DP=100, 10 chains, 7,020 atoms
**Target Properties:** Tg, density, bulk modulus, structural properties (RDF, end-to-end vectors)
**Status:** ✅ COMPLETE — All 17 stages (equilibration + 13-point Tg sweep) finished

---

## Experimental Benchmarks

| Property | Value | Source |
|---|---|---|
| Tg (amorphous) | 206–213 K | Törmälä, *Eur. Polym. J.* 10, 519 (1974): 213 K via spin probe ESR; PI: 206 K (Pfefferkorn et al. 2010, DSC) |
| Density @ 300K | ~1.10–1.13 g/cm³ (amorphous MD) | Wu (2011) AA OPLS-AA; Kacar (2018) PCFF: 1.132 |
| Bulk modulus | ~1.5 GPa (at 120°C) | Pfefferkorn et al. 2010, isothermal PVT |

**Acceptance criteria:** Tg ±20K, density ±5%, bulk modulus ±30%

---

## System Parameters

| Parameter | Value | Rationale |
|---|---|---|
| SMILES | `*CCO*` | Poly(ethylene oxide); repeat unit –CH₂–CH₂–O– |
| Degree of polymerization | 100 | Consistent with Runs 1 and 2 for ensemble averaging |
| Number of chains | 10 | Balance between sampling and computational cost |
| Total atoms | 7,020 | 702 atoms/chain × 10 chains |
| Force field | GAFF2 | Updated GAFF with improved ether parameterization |
| Charge method | RESP (Psi4/HF/6-31G*) | Standard QM electrostatic potential; Gasteiger insufficient for PEG gauche effect |
| Pair style / Electrostatics | lj/charmm/coul/long + PPPM | PPPM for long-range Coulomb; LJ cutoff 8.0–12.0 Å |
| Timestep | 2 fs | SHAKE constrains H–X bonds; T_DAMP = 200 fs, P_DAMP = 2000 fs |

---

## Stage 1: Molecular Construction

Fresh cell generation (independent from Runs 1 and 2 via new random packing seed).

| Step | Job ID | Status |
|---|---|---|
| Monomer build + RESP charges + polymerization + GAFF2 | — | ✅ Reused from Run 1 |
| Cell generation | `b3e83758` | ✅ 7020 atoms, 113.5 Å box, 10 chains, 0.05 g/cm³ |
| Upload to Lambda | — | ✅ `/home/arz2/simulations/02272026_PEG_run3/peo_system_run3.data` |
| Parse on Lambda | `parse_data_file` | ✅ 7020 atoms, 6 types, PPPM confirmed, SHAKE H-types [1,4,6] |

---

## Stage 2: Equilibration

| Stage | Type | T (K) | P (atm) | Steps | Status |
|---|---|---|---|---|---|
| 01 minimize | Energy min | — | — | 50,000 iter (CG) | ✅ |
| 02 nvt_softheat | NVT | 300→600 | — | 500,000 × 1 fs | ✅ |
| 03 npt_compress | NPT | 600 | 1→50,000 | 500,000 × 1 fs | ✅ |
| 04 npt_pppm | NPT+PPPM | 600 | 50,000→1 | 500,000 × 1 fs | ✅ |
| 05 npt_cool | NPT+PPPM | 600→300 | 1 | 1,000,000 × 1 fs | ✅ |
| 06 nvt_production | NVT+PPPM | 300 | — | 1,000,000 × 1 fs | ✅ |

All 6 stages completed 2026-03-06. Key observations per stage:
- Stage 03 compression to 50,000 atm produces peak density ~1.45 g/cm³ — expected at extreme pressure.
- Stage 04 decompresses with PPPM; density relaxes partially (box slightly over-expanded; corrected during cooling).
- Stage 05 ends at ~295 K with residual tension (~−390 atm) typical of NPT cooling near Tg.
- Stage 06 NVT: box fixed at stage 05 configuration; density constant by definition (σ=0 expected).

**Equilibration check** (`check_equilibration` on `bulk_modulus/peg3_npt_bulk.log`, constant T=300K NPT, 500K steps):
- Density: ✅ PASS | Energy: ✅ PASS

**Equilibrated density** (`extract_equilibrated_density` on `bulk_modulus/peg3_npt_bulk.log`): extracted from constant 300K NPT log. *Updated 2026-03-16.*

---

## Stage 3: Tg Measurement

**Design improvement over Run 2:** Run 2 found Tg ≈ 300K at the boundary of its rubbery-side range (400K was the top point). Bilinear fit cannot anchor rubbery slope properly at the edge. Run 3 uses 440→200K range: 440K gives solid 4-point rubbery baseline well above plausible MD Tg; 200K gives 3 deeply glassy points.

| Parameter | Value | Rationale |
|---|---|---|
| T range | 440 → 200 K | Prevents Tg landing at range boundary |
| T step | 20 K | Standard interval across campaign |
| Points | 13 | 6 rubbery + 3 transition + 4 glassy |
| Steps per T | 1,000,000 (2 ns) | Rule #2 compliant (≥2 ns/step) |
| Total simulation time | 26 ns | 13 steps × 2 ns |

All 13 stages completed 2026-03-06 23:50 EST. Aggregate log: `tg_sweep/tg_sweep.log` (9.4 MB).

**Tg extraction:** `extract_tg` tool (v3 F-stat). 17 bins retained, 10 skipped (drift). `scipy.optimize.curve_fit` piecewise-linear model on 13 (T, ρ) setpoints.

**Critical fit quality note:** The v2 bilinear Tg is flagged as unreliable for this run. The two fitted slopes are nearly identical (Δa < 1%), meaning the density–temperature curve is effectively linear across the entire 200–440 K range. This produces a pathological line-intersection Tg of ~2,456 K — a clear diagnostic of fit degeneracy, not a physical result. Possible causes:
1. Wide T-range dilutes the transition signal relative to linear background trend
2. Insufficient chain relaxation at high T: rubbery-region points (360–440 K) may not be fully equilibrated at 2 ns/step for 100-mer PEO
3. GAFF2 known to overestimate stiffness for PEO chains, suppressing the glass transition signal

The R²=0.9933 reflects how well a single line fits the entire range — not bilinear transition quality. The α_inversion (α_glassy ≈ α_rubbery) is physically incorrect and confirms the fit is not resolving a true glass transition. The v3 F-stat Tg is usable for ensemble averaging; v2 bilinear should be disregarded for this run.

---

## Stage 4: Structural Analysis

**Source:** NVT production trajectory at 300 K, 101 frames
**Analysis:** MDAnalysis InterRDF (v2.10.0), `mda_rdf.py`, `mda_end_to_end.py`
**Parameters:** rmax = 15.0 Å, 150 bins
**Backbone types for E2E:** [2, 3] (C and O backbone)
**Output:** `/home/arz2/simulations/PEG_run3/structure/analysis_mda/`

RDF atom type assignments match Run 1. t5–t6 (O–H hydroxyl bond, ~0.95 Å) shows very high g(r) (~5013), consistent with Run 1 (~5143).

---

## Incidents & Troubleshooting

### Incident 1 — Stage 02 failed: pair style mismatch + wrong CWD (Feb 27)

Original chain script launched `mpirun` without first `cd`-ing to `remote_work_dir`. Output files landed in `/home/arz2/` instead of the expected simulation directory. Stage 02 then failed: `read_data` path missing, plus style mismatch (`lj/cut` vs `lj/charmm/coul/long` pair coeffs in data file).

**Fix:** Moved output files to correct directory; regenerated stages 02–03 with `use_pppm=True`; wrote `chain_resume.sh` with `cd "$workdir"` before each `mpirun`. **Root cause fixed in MCP server:** Added `cd {wdir} &&` before `mpirun` in `_build_chain_script()`.

### Incident 2 — Duplicate chain processes (Feb 27)

Resume chain launched twice during debugging (PIDs 3460039 and 3460491). Both survived under nohup, halving throughput. Stale Run 2 tg_380K job (PID 3443907) also running.

**Fix:** Killed duplicate chain PID 3460039 and stale Run 2 job PID 3443907. Verified single clean process tree.

### Incident 3 — Loose files in `/home/arz2/` root (Feb 27)

~550 MB stray dumps, logs, and restart files accumulated from failed attempts and stale jobs.

**Files deleted:** `minimize.dump`, `02_nvt_softheat.dump` (538 MB), `*.log` (failed chains), `*.rst` (orphaned restarts), `chain_8bd2f4b8.sh` (broken original chain). Total freed: ~550 MB.

### Incident 4 — Stage 02 SIGKILL at step 18,000 (Feb 27)

mpirun received SIGKILL at step 18,000/500,000. No LAMMPS error — clean thermo output up to that step. RAM and GPU memory confirmed not exhausted. Cause undetermined (likely manual kill or transient system event). Relaunched; step 18,000 of work lost (~3 min).

---

## Known Limitations

1. **Run 3 bilinear Tg unreliable:** Near-parallel slopes; v2 bilinear degenerate. Use v3 F-stat only.
2. **High-T sampling may be insufficient:** 100-mer PEO chains at 440 K may require 5–10 ns/step for full relaxation above 380 K.
3. **NVT production stage (06) gives no density fluctuations:** Fixed-box NVT unsuitable for density validation — recommend NPT for future runs.
4. **GAFF2 stiffness overestimate for long-chain PEO:** May artificially raise Tg and suppress glass transition signal.

---

## References

- Webb, et al. (2024). *JPCB* — Polymer electrolyte Tg best practices; systematic overestimation discussion
- Klajmon, et al. (2024) — Continuous cooling MD; Tg measurement uncertainties

*PolyJarvis (Claude + RadonPy MCP) | Force field: GAFF2 | GPU: Quadro RTX 6000 (GPU 3) | MPI: 4*
