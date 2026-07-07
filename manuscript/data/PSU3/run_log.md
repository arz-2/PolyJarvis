# Polysulfone (PSU/Udel) Run PSU3 · 2026-06-24 → 2026-06-26
SMILES: `*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1`  |  FF: PCFF  |  Charges: none (bond-increment)  |  DP: 25  |  Chains: 8  |  GPU: 3
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=734512  |  SEED_HOT=171894  |  SEED_COLD=291434
Plan: `data/PSU3/raw/run_plan.json`  |  mode: reasoned  |  confidence: medium  |  critic: approved (round 1, 0 findings)  |  T_workflow_K: 700  |  is_glassy: true (exp Tg=463 K)

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                | classify_polymer → PSFO → EMC PCFF auto-routed (use_pcff=true) |
| D-02 Charges        | bond-increment (embedded in PCFF)        | EMC Class-II FF: charges embedded, no QM step |
| D-03 Electrostatics | PPPM 12 Å                          | aryl-SO2-aryl + ether heteroatom charges → long-range Coulomb |
| D-04 System size    | DP=25, 8 chains, 10816 atoms                        | polymer_rules.json PSFO default (DP≥20 Fox-Flory floor) |
| D-05 Convergence    | PASS (after EXTEND×1)                         | 2 ns NPT extension → density 1.1825→1.1840 g/cm³ (SEM 0.021%, drift 0.12%). Hard gates (density SEM/CV/P2/energy) PASS; Rg CV 36.5% + density-homog CV 25.1% are marginal finite-size (DP=25, N=8), advisory for rigid aromatic. Recheck 1/2 → PASS |
| D-06 Tg fit quality | per-rate all GOOD/EXCELLENT  | r25 Tg=502.0 K (R²=0.9929 GOOD); r50 Tg=534.6 K (R²=0.9972 EXC); r100 Tg=496.8 K (R²=0.9965 EXC). is_glassy=true (from plan exp-Tg 463 K, since slope-gate failed → MD Tg must not decide routing) |
| D-06b Multirate Tg  | SLOPE-GATE FAILED → single_rate_fallback Tg=502.0 K  | log-linear Tg(Γ) slope=−3.75 K/ln(K/ns), R²=0.016, N_rates=3 @ [25,50,100] K/ns (0.60-decade span). Non-monotonic (r50 high outlier, r25≈r100 inverted) → slope ≤0 → glassy slope-gate FAIL. VF=FAILED (<2 decades). Staged registry rows held (NOT committed) per deferred-write rule. tg_at_slow_rate_K=502.0 K (slowest/most-equilibrated rate, +8.4% vs exp 463 K). **USER DECISION (budget): accept 502 K with slope-gate-failed/low-confidence caveat and finish the run** (full recovery ~23.5h would exceed the 48h budget; ~13h left). Staged registry rows DISCARDED (not committed — contaminated, would bias cross-run multirate fits). Headline Tg flagged unreliable. |
| D-07 Property method | murnaghan (glassy 300 K) | is_glassy=true (from exp Tg 463 K > 300, since slope-gate failed → MD Tg must not decide routing). Glassy primary → Murnaghan NPT compression at 300 K on post-extend cell npt_extend_out.data |
| D-07 Property method | [born (glassy) / deform fallback (glassy) / murnaghan (rubbery) / fluctuation (rubbery fallback) / N/A] | [Tg=[X] K → is_glassy=[true/false]; bm_pressures_atm=[Y/N] / N/A — bulk_modulus not requested] |

<!-- Example — PS1 completed run:
| D-01 | PCFF | classify_polymer returned PSTR → EMC PCFF auto-routed |
| D-02 | bond-increment | PCFF: bond-increment charges embedded, no QM step |
| D-03 | pppm 12 Å | Aromatic ring partial charges → long-range Coulomb |
| D-04 | DP=40, 10 chains, ~6400 atoms | polymer_rules.json default |
| D-05 | PASS | density drift 0.4% over last 500 ps; energy plateau confirmed |
| D-06 | ACCEPTABLE | R²=0.93, F-stat GOOD, N=19 bins; range 550→250K in 20K steps |
-->

<!-- Add rows for any non-routine decisions (parameter overrides, custom protocols, etc.) -->

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts) -->

**R-01 · Tg sweep r25 — read_data path not found (recovery 1/2)**
- Symptom: tg_sweep r25 (run e9e27819) failed instantly, exit 1. `tg_sweep.log`: `ERROR: Cannot open file data/PSU3/lammps/equil/npt_extend/npt_extend_out.data: No such file or directory` at `read_data`.
- Root cause: generate_script wrote the **relative** data path into the `.in`; the LAMMPS process runs from `tg_sweep_r25/`, so the repo-relative path doesn't resolve. The file exists at the absolute path.
- Fix: re-submit tg-sweep-worker with the **absolute** data path (`/home/alexzhao/PolyJarvis/data/PSU3/lammps/equil/npt_extend/npt_extend_out.data`) in both prompt header and the generate_script `data_file=`.
- Outcome: re-submitted (R-01). No GPU time lost (failure was at read_data, before any dynamics).

**R-02 · Tg sweep r50 — gpu-package deck line on kokkos engine (recovery 1/2)**
- Symptom: tg_sweep r50 (run 83eae966) failed instantly: `ERROR: Package gpu command without GPU package installed`. Deck line 25 = `package gpu 1 neigh no`.
- Root cause: generate_script rendered the gpu-package deck instead of the kokkos deck (engine="kokkos" not threaded). The working r25 deck has `# KOKKOS: package loaded via -pk kokkos` at line 25; r50 had the active `package gpu` line. KOKKOS loads the package via `-pk kokkos` on the CLI, so any `package gpu` line is fatal (gpu package not compiled in).
- Fix: full-diff confirmed line 25 was the ONLY substantive difference vs the working r25 deck; sed-replaced `package gpu 1 neigh no` → kokkos comment (no live writer, lsof clean), then resubmit the corrected .in via run_lammps_script (no regenerate, to avoid re-introducing the bug).
- Outcome: re-submitted (R-02). No GPU time lost (failed before dynamics).

**R-03 · Murnaghan BM — GPU-3 contention with concurrent PEEK4 run → too slow for budget (recovery 1/2)**
- Symptom: Murnaghan chain 6c5ee4f8 (5×500k steps) ran at ~107k steps/hr (bm_P-1000: step 112k in 63 min) — ~12× slower than the kokkos Tg sweeps (~1.4M/hr). Full series projected ~23h vs ~9.5h budget remaining.
- Root cause: nvidia-smi/lsof showed GPU 3 shared by a concurrent **PEEK4** BM lmp (pid 4067061) alongside PSU3's lmp — GPU contention. Compounded by BM dump-file I/O (the Tg sweep wrote no dumps). Engine was correctly kokkos (verified chain.sh: lammps-install-kokkos + -sf kk -pk kokkos); not an engine fallback.
- Fix: killed ONLY the PSU3 BM pids (4070804/4070810/4070796, each PSU3-confirmed via /proc cwd+cmdline); left PEEK4 untouched (rule 3). Cleaned partial output. Resubmitted with npt_steps=150000 (0.15 ns/point, 5 pts → 750k steps ≈ 7h even under contention; glassy cell volume converges fast, eq_fraction=0.5 → 75 ps avg). is_glassy unchanged.
- Outcome: re-submitted (R-03).

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage) | b617e91c | 19:47 | 01:50 | ~6h | done |
| equil-extend (2ns) | db36267e | 02:35 | 03:30 | ~1h | done → equil PASS |
| tg-sweep r25 (seed 465836) | e9e27819 | 03:45 | 04:14 | — | failed (rel path) |
| tg-sweep r25 retry (seed 778250) | b1d29518 | 04:20 | ~17:30 | ~13h | done (26/26) |
| tg-sweep r50 (seed 363586) | 83eae966 | 17:40 | 17:41 | — | failed (gpu-pkg deck) |
| tg-sweep r50 retry (seed 363586, deck-fixed) | 57622545 | 17:45 | 00:55 | ~7h | done (26/26) |
| tg-sweep r100 (seed 735390) | c76aefc6 | 02:25 | 05:55 | ~3.5h | done (26/26) |
| murnaghan BM (±1000 atm, 5pt×500k) | 6c5ee4f8 | 06:10 | 09:45 | — | killed (GPU contention, too slow) |
| murnaghan BM retry (±1000 atm, 5pt×150k) | 33df09f7 | 09:50 | 16:42 | ~7h | done (5/5) |

**RUN COMPLETE** 2026-06-26 ~16:50. run_summary: `data/PSU3/raw/run_summary.json`. Density PASS ✓, K PASS ✓, Tg FAIL/⚠ (flagged unreliable — slope-gate failed, user-accepted single-rate fallback). GPU 3 released.

GPU claim label: `PSU3` (claimed GPU 3 via pick_gpu.py)
GPU inventory (`nvidia-smi` at run start): GPU 3: NVIDIA A800 40GB Active, 40 GB, ~40 GB free

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=300.09 K · 1951 frames analysed (skip=50) · 2026-06-25 02:02 · pre-EXTEND

**Overall: PASS after EXTEND×1** (pre-extend snapshot below; 2 ns NPT extension at 300 K → density 1.1825→1.1840 g/cm³, SEM 0.021%. Hard gates pass; marginal Rg/density-CV are DP=25 finite-size, advisory for rigid aromatic backbone.)

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1153% (p=0.0002) | <1%, p<0.01 | PASS |
| Energy drift | 0.0345% (p=0.481) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0285% | <1% | PASS |
| Energy block-SEM | 0.0096% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 36.5% | <30% | FAIL (marginal, N=8) |
| MSID slope | 1.026 (R²=0.9923) | 1.0 ±20% | OK |
| C(t) τ_relax | 19471772.4 ps (2% decayed) | — | ⚠ partial (aromatic, advisory) |
| MSD kinetic trap | yes (α=0.226, MSD=666.09 Å²≫Rg²=1260.449) | — | ⚠ trapped (expected glassy) |
| R_ee mean ± std | 83.89 ± 44.66 Å (N=8 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0225 ± 0.0046 | <0.10 | PASS |
| Density homogeneity CV | 25.1% (8³ grid, 21.1 atoms/voxel) | <25% | FAIL (marginal, Poisson-limited) |

**Warnings:** C(t) partially decayed (2% — aromatic backbone, advisory only); MSD kinetically trapped (expected below Tg, not a structural failure).

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | CV 36.5% (N=8 chains) | CV < 30% → FAIL (marginal finite-size) |
| MSD plateau   | kinetically trapped (α=0.226) | expected below Tg |
| Density homog (CV) | 25.1% | < 25% → FAIL (marginal, Poisson 21.8% baseline) |
| C(t) decay (melt NVT) | 2% (τ_relax 1.95e7 ps) | advisory — aromatic main chain |
| τ_c chain relax (KWW) | 1.95e7 ps | annotation only |
| R_ee mean ± std | 83.89 ± 44.66 Å (N=8 chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.1840 g/cm³ | ~1.24 g/cm³ | −4.5% | NPT 300K plateau (post-extend) | ✓ |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (slowest rate, 25 K/ns) | 502 K ⚠ UNRELIABLE | 463 K (PSU/Udel) | +8.4% | bilinear fit, r25 (GOOD R²=0.9929). **Slope-gate FAILED** (non-monotonic Tg vs rate; multirate DSC-extrap invalid) — value is single-rate fallback, low confidence | ⚠ |
| Tg per-rate (MD) | r25=502.0, r50=534.6, r100=496.8 K | — | — | non-monotonic over 0.60-decade span → slope −3.75 K, R²=0.016 | annotation |
| α_g (CTE) @r25 | 2.24×10⁻⁴ K⁻¹ | ~5–7×10⁻⁵ (lit) | high | −a_glassy / ρ_mean_glassy (note: aromatic backbone CTE) | ⚠ |
| α_r (CTE) @r25 | 4.68×10⁻⁴ K⁻¹ | — | — | −a_rubbery; CTE ratio α_r/α_g=2.08 (healthy) | annotation |
| ΔCp at Tg @r25 | 0.126 J/(g·K) | ~0.17–0.28 (lit) | — | H(T) bilinear fit | ⚠ |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 4.42 ± 0.07 GPa | 4.0–5.5 GPa    | within range | Murnaghan EOS (5pt ±1000 atm, 300 K; r²=0.9996). B_dyn fluctuation cross-check 4.37 GPa (1.1% agree) | ✓ |
| B0' | 18.79     | 7–11 (typical) | —    | Murnaghan fit; elevated (narrow ±1000 atm span under-constrains curvature at 0.15 ns/pt) — WARNING not FAIL, K robust | annotation |
| G   | N/A | —    | — | deformation not run (Murnaghan path; no budget for deform)               | N/A |
| E   | N/A | 2.5–2.6 GPa (Mark)    | — | deformation not run               | N/A |

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 40.1 h  |  **GPU**: 40.1 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PSU3/lammps/**/*.log` (Born stages excluded); reproducible via `manuscript/gen_table_compute_cost.py`.
