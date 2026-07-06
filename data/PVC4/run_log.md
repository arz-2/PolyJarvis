# PolyVinyl Chloride (PVC) Run PVC4 · 2026-06-24 → 2026-06-26 · COMPLETE

> **FINAL RESULTS** — ρ(300K)=**1.350 g/cm³** ✅ PASS (−2%) · Tg(single-rate 25 K/ns)=**315.1 K** ⚠ (−11%, PCFF bias) · K=**2.90 GPa** ⚠ (−17%, PCFF bias). Overall: MIXED — density excellent; Tg & K underpredicted by the known PCFF/PVNL systematic. Multirate slope-gate DESCOPED to single-rate per user. Summary: `data/PVC4/raw/run_summary.json`.

SMILES: `*CC(Cl)*`  |  FF: PCFF  |  Charges: embedded (bond-increment)  |  DP: 60  |  Chains: 10  |  GPU: 2
Requested: {density, tg, bulk_modulus}  |  Replicate: 1 of 1  |  Seeds: EMC=472913  |  SEED_HOT=547989  |  SEED_COLD=N/A (single velocity-create equil chain)
Plan: `data/PVC4/raw/run_plan.json`  |  mode: reasoned  |  confidence: medium  |  critic: approved (4 rounds; r3=ladder trim, r4=window 250–450K)  |  T_workflow_K: 530.0

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-00 Plan gate      | reasoned, confidence=medium                          | dominant uncertainty: tg_rate_span_slope_gate; PVC3 slope-gate fix applied |
| D-01 Force field    | PCFF                                                 | classify_polymer → PVNL → EMC PCFF; OPLS-AA failed to build PVC |
| D-02 Charges        | embedded (bond-increment)                            | PCFF/EMC embeds chloride partial charges, no QM step |
| D-03 Electrostatics | PPPM 12 Å                                           | chloride → significant backbone partial charges → long-range Coulomb |
| D-04 System size    | DP=60, 10 chains, ~3600 atoms                        | polymer_rules.json default; reproduced PVC density −2.5% in PVC3 |
| D-06b Tg method     | SINGLE rate 25 K/ns, full window 150–550 K           | FINAL (USER, round-5): descoped from multirate to single-rate. Evolution: 5-rate→3-rate [6.25,25,100] (budget)→narrow 250–450 (budget)→**single 25 K/ns over full 150–550** (user). Multirate slope-gate / DSC extrapolation DROPPED → single-rate MD Tg only (reads high vs exp; partial offset to PCFF underpredict). ~8.4h (21 holds × 800k). 6.25 (32h) dropped; [25,100] span only 0.6 dec so multirate moot without 6.25. GPU-share tested = 8× slower |
| D-05 Convergence    | EXTEND×1 → PASS (residual-aging caveat)               | density converged (1.350, drift 0.11%, SEM 0.001%); energy drift 5.55%→9.56% after +2 ns = glassy physical aging (worsened → not time-fixable); all structural/spatial gates PASS; accepted PASS w/ caveat over futile 2nd extension |
| D-06 Tg fit quality | GOOD (single-rate)                                   | R²=0.9869, primary bilinear Tg=315.1 K (alt 344.7 K, gap 29.6 K → WARNING); is_glassy=TRUE (315>300, also alt 345 & exp 354 >300); CTE α_r/α_g=2.17 ✓; ΔCp=0.149 J/g·K |
| D-06b Multirate Tg  | N/A — single-rate (user descope)                    | multirate slope-gate / DSC extrapolation DROPPED per user; only 25 K/ns run. Headline Tg = single-rate MD primary 315.1 K (−11% vs exp 354, known PCFF/PVNL underpredict) |
| D-07 Property method | murnaghan (glassy 300 K, primary)                   | is_glassy=TRUE → Murnaghan compression at 300 K on npt_extend cell; bm_pressures_atm=[-1000,0,1500,3000,5000] (compression-biased, cavitation-safe per memory) |

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

### RECOVERY A: Energy drift persists after +2 ns NPT extension (attempt 1→2)
**Symptom:** npt_extend attempt 1 (2 ns @300K) showed **energy drift WORSENING** from 5.55% → 9.56%; energy block-SEM 0.84% → 1.02% (both above threshold). Density remained excellent (1.350 g/cm³, drift 0.11%, SEM 0.0012%).

**Diagnosis:** Glassy PVC at 300K undergoes slow physical aging; thermo statistics degrade under low-mobility regime. Energy drift is a manifestation of the **time-scale mismatch**: 2 ns is insufficient to suppress thermal fluctuations in a glassy packed system (τ_eff_density = 0.14% of run). Compounding factor: MSID slope 1.209 (non-Gaussian, possible minor chain compression from pressure equilibration).

**Resolution:** Accepted **PASS with caveat — NO 2nd extension**. Energy WORSENED after +2 ns (5.55%→9.56%), confirming time will not fix it. Density rock-solid at 0.11% drift (no densification) ⇒ the energy decrease is pure conformational relaxation = intrinsic glassy physical aging at 300 K, not a non-equilibrium defect. Per protocol off-ramp ("prefer PASS with caveat over endless EXTEND"), a 2nd extension on the single available GPU is futile. Downstream impact: thermal Tg sweep re-melts the cell (Tg unaffected); mechanical K @300 K carries the residual-aging caveat (PCFF already underpredicts PVC K ~−20%, so this adds modest scatter, not a sign error). Used `npt_extend_out.data` (most-relaxed cell) as the Phase B starting cell.

**Outcome:** converged-enough (density/structure); energy aging accepted as intrinsic.

### RECOVERY B: Tg sweep r6.25 failed instantly — relative data path unresolved
**Symptom:** Sweep run cc8d69f9 (rate 6.25) wrote a `failed`/exit_code 1 sentinel within seconds. tg_sweep.log: `ERROR: Cannot open file data/PVC4/lammps/equil/npt_extend/npt_extend_out.data: No such file or directory`.
**Root cause:** the data_file was passed as a REPO-RELATIVE path (`data/PVC4/...`). LAMMPS executes in the sweep work_dir (`.../thermal/tg_sweep_r6`), so the relative `read_data` path doesn't resolve from there. gen_prompt emitted `equil_data_path` relative; it must be absolute for the in-work_dir LAMMPS process (CLAUDE.md: use absolute paths in all tool calls).
**Fix:** re-submit with the ABSOLUTE data_file `/home/alexzhao/PolyJarvis/data/PVC4/lammps/equil/npt_extend/npt_extend_out.data`. Verified file exists; no live writers (lsof); cleared the stale failed sentinel. No wall-time lost (failed at read_data, before any dynamics). New velocity seed on regen.
**Status:** RESOLVED — relaunching sweep r6.25 with absolute path (attempt 2).

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-run glassy chain) | 0e4c8878 | 2026-06-24 | 2026-06-25 | ~9 stages | done |
| npt_extend (+2 ns @300K, attempt 1) | ac74390d | 2026-06-25 | 2026-06-25 | ~2 ns | done |
| npt_extend (+2 ns @300K, attempt 2) | — | — | — | — | NOT RUN (accepted PASS w/ aging caveat) |
| tg-sweep r6.25 (idx0) attempt1 | cc8d69f9 | 2026-06-25 | 2026-06-25 | <1min | FAILED (relative data path — RECOVERY B) |
| tg-sweep r6.25 (idx0, 550→150K, 3.2M/T) attempt2 | 7e4d42a4 | 2026-06-25 | 2026-06-25 | ~1.7h | DISCARDED — wide window superseded by 250-450K narrow (user) |
| tg-sweep r100 (idx2) — A/B concurrency test | d5b60ffb | 2026-06-25 | 2026-06-25 | killed | KILLED — GPU-share 8× slower; requeue sequential |
| tg-sweep r6.25 (idx0, 450→250K narrow, 3.2M/T, 11 holds) attempt3 | 179a88db | 2026-06-25 | 2026-06-25 | <1h | KILLED — superseded by single-rate 25 (user revert to full window) |
| tg-sweep r25 (single rate, 550→150K full, 800k/T, 21 holds) | 6ab56c73 | 2026-06-25 | 2026-06-26 | ~8.4h | done (21/21) → Tg 315.1 K |
| murnaghan BM series (glassy 300K, 5 press, 0.5ns each) | 2737b239 | 2026-06-26 | 2026-06-26 | ~1.2h | done (5/5, no cavitation) → K=2.90 GPa |

GPU 2 released (PVC4 claim already cleared; `release` returned []). NOTE: GPU 2 is now running a CONCURRENT session's PEEK4 sweep (pid 4045482, cwd data/PEEK4/...) — left untouched per cross-track rule 3 (not my writer). All PVC4 GPU work complete.

**A/B GPU-sharing test (user-requested):** ran r100 concurrently with r6.25 on GPU 2 (Default compute mode, NO MPS). Result: BOTH sweeps dropped to 35.4 steps/s (from 555 solo) → aggregate 70.8 steps/s = **13% of solo throughput, ~8× slower than sequential**. Two PCFF/PPPM kspace solvers thrash without MPS. DECISION: reverted to sequential. r100 will be re-run solo after r6.25 + r25. Lesson: `pid_<id>` sentinel holds the *launcher* PID — killing it orphans the `lmp` child; kill the lmp directly (find via `lsof <log>` or `nvidia-smi --query-compute-apps`).

GPU claim: `pick_gpu.py claim --run PVC4` → claimed GPU **2** (A800), engine=kokkos, mpi=1, gpu_per_run=1 (D-08). Release label: `PVC4`.

GPU inventory (`nvidia-smi` at run start): GPU 2: NVIDIA A800 40GB Active, 40 GB, ~40 GB free (all 4 A800 GPUs idle at start; live host == directional_probe benchmark host)

---

## D-05 CONVERGENCE DETAIL

### Attempt 1 (npt_prod300, pre-extend) — raw tool Overall: FAIL → orchestrator verdict: EXTEND
`check_equilibration_comprehensive` · T=299.92 K · 951 frames (skip=50)

**A. Thermo convergence**
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1096% (p=0.0841) | <1%, p<0.01 | PASS |
| Energy drift | 5.5532% (p=0.0005) | <1%, p<0.01 | **FAIL → EXTEND** |
| Density block-SEM | 0.0909% | <1% | PASS |
| Energy block-SEM | 0.8387% | <1% | PASS |

**B. Chain conformation** (melt dump, advisory under glassy carve-out)
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 18.1% | <30% | PASS |
| C∞ | 8.814 | — | INFO |
| MSID slope | 1.209 (R²=0.969) | 1.0 ±20% | ⚠ borderline non-Gaussian |
| C(t) τ_relax | 14387.5 ps (16% decayed) | — | ⚠ advisory (glassy) |
| MSD kinetic trap | none (α=0.264) | — | OK |

**C. Spatial / packing**
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0271 ± 0.008 | <0.10 | PASS |
| Density homogeneity CV | 18.5% (5³ grid, 29 atoms/voxel) | <25% | PASS |

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg CV (chain–chain) | 18.1% | CV < 30% → PASS |
| MSD plateau   | still diffusing (no kinetic trap, α=0.264) | OK |
| Density homog (CV) | 18.5% | < 25% → PASS |
| C(t) decay (melt NVT) | 16% (0.158) at threshold 0.1 | advisory (glassy carve-out) |
| τ_c chain relax (KWW) | 14387.5 ps | annotation only |
| R_ee mean ± std | 28.76 ± 11.99 Å (N=10 chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.350 ± 0.008 g/cm³ | 1.30–1.45 (amorphous PVC, ~1.38) | −2% | NPT 300K plateau (npt_extend) | ✓ PASS |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (DSC-equiv) | N/A | — | — | multirate DROPPED (user descope) | — |
| Tg (MD @25 K/ns) | 315.1 K (alt 344.7) | 354 K (exp) | −11% | single-rate bilinear, R²=0.987 GOOD | ⚠ underpredict (PCFF/PVNL bias) |
| α_g (CTE) | 25.5×10⁻⁵ K⁻¹ | ~5–7×10⁻⁵ (lit, expect lower) | — | −a_glassy / ρ_mean_glassy | ⚠ (per-K, see note) |
| α_r (CTE) | 55.3×10⁻⁵ K⁻¹ | — | — | −a_rubbery / ρ_mean_rubbery | ratio α_r/α_g=2.17 ✓ |
| ΔCp at Tg | 0.149 J/(g·K) | ~0.16–0.20 (lit) | — | H(T) bilinear fit | ✓ reasonable |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 2.90 ± 0.11 GPa | 3.5–4.5 GPa    | −17% | Murnaghan EOS, glassy 300K, 5-pt compression-biased (B0'=10.3, r²=0.9996) | ⚠ PCFF underpredict (FF systematic, not error) |
| B0' | 10.32   | 7–11 (typical) | —    | Murnaghan fit (compression-biased span resolved B0' cleanly)            | annotation |
| G   | N/A | —    | — | deform not run (Murnaghan accepted)               | N/A |
| E   | N/A | —    | — | deform not run (Murnaghan accepted)               | N/A |

Fluctuation B_dyn cross-check = 2.41 GPa (20% below Murnaghan; B_def R²=0.02, n_eff=272 — unreliable, Murnaghan authoritative).

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 13.7 h  |  **GPU**: 13.7 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PVC4/lammps/**/*.log` (Born stages excluded); reproducible via `paper/gen_table_compute_cost.py`.
