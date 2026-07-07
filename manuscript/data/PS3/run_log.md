# Atactic Polystyrene (PS) Run PS3 · 2026-06-23 → 2026-06-24
SMILES: `*CC(c1ccccc1)*`  |  FF: PCFF  |  Charges: bond-increment (EMC)  |  DP: 40  |  Chains: 10  |  GPU: 1 (claim label PS3)
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=472913  |  SEED_HOT=[N]  |  SEED_COLD=[N]
Plan: `data/PS3/raw/run_plan.json`  |  mode: reasoned  |  confidence: medium  |  critic: approved (1 round)  |  T_workflow_K: 550
D-08 hardware: engine=kokkos, gpu_per_run=1, mpi=1 (confidence=low, host mismatch)

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                | classify_polymer returned PSTR → EMC PCFF auto-routed (preferred over TraPPE-UA for aromatic ring charges) |
| D-02 Charges        | bond-increment (embedded in PCFF) | EMC class-II FF: bond-increment charges embedded, no QM step |
| D-03 Electrostatics | PPPM, 12 Å cutoff   | Aromatic ring partial charges → long-range Coulomb |
| D-04 System size    | DP=40, 10 chains, 6420 atoms | polymer_rules.json default; note DP40 < Me(160) → K screening-grade |
| D-05 Convergence    | PASS                         | overall_pass=true; structural+thermo gates pass; C(t) advisory only (glassy carve-out, DP40≥30) |
| D-06 Tg fit quality | GOOD (per-rate, r400)  | R²=0.993, N=23 bins, fit=GOOD; is_glassy=TRUE (Tg@400K/ns=404.3 K > 300 K → mechanical track unblocked) |
| D-06b Multirate Tg  | Tg≈376 K (slowest-rate + VF Γ→0; DSC extrap UNRELIABLE) | log-linear Tg(Γ) b=+11.16 K/ln(K/ns), R²=0.673, N_rates=3 @ [40,160,400] K/ns, N_repl=1; slope_gate PASS. DSC log-linear extrap=80 K REJECTED (R²<0.90, 1-decade span). Reported: MD@40K/ns=376.5 K (GOOD) ✓ + VF Tg₀=375.5 K ✓ — both in exp 373–383 K. VF quality=POOR_POORLY_CONSTRAINED (CI=∞, <2 decades). See RECOVERY block. |
| D-07 Property method | murnaghan (glassy 300 K, ±1000 atm) | is_glassy=TRUE (Tg@400K/ns=404 K); 5-point EOS, B0'=13.57∈[4,20], R²=0.998, fit_converged — no deform fallback |

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

## RECOVERY — analyze-tg-multirate attempt 1
- **Trigger:** multirate log-linear R²=0.6726 < 0.90 plan gate (success_criteria.loglinear_r_squared_min); DSC extrapolation → 80 K (unphysical over 11 decades).
- **Diagnosis:** NOT a simulation error. All 3 per-rate bilinear fits are GOOD/EXCELLENT (R²>0.99). Root cause is an intrinsic limitation: the 3 rates [40,160,400] K/ns span only **1 decade**, and r400 shows high-rate Tg saturation (404.3 K vs ~377 K for the two slower rates). The tool itself flags `vf_fit_quality=POOR_POORLY_CONSTRAINED` ("<2 decades"). The recovery-taxonomy options don't apply: per-rate fits are already excellent (no noisy sweep to re-run), and a rate IS its steps/T (can't add steps without changing the rate). Only a wider rate span (a ~10 K/ns 4th sweep, ~20 GPU-h) would tighten the extrapolation.
- **Action:** Accept the slowest-rate MD Tg = **376.5 K** as the reported Tg (most-equilibrated, closest to DSC), corroborated by the VF zero-rate limit Tg₀ = 375.5 K. Both land in the experimental range (373–383 K). The DSC log-linear extrapolation (80 K) is flagged UNRELIABLE and NOT reported. slope_gate PASSES (slope=+11.16 K/ln, physically correct direction — unlike the prior PSTR/PCFF inversion in memory). User confirmed this resolution (vs. a 20-GPU-h re-plan that would not change the ~376 K conclusion). No further sims.
- **Outcome:** converged (Tg accepted with caveat; matches experiment)

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage chain) | c2a94ebb | 15:43 | 20:45 | 5h 02m | done |
| tg-sweep r40 (21 T)  | 8de51024 (GPU1, label PS3_tg40)  | 21:05 | 02:51 | 5h 46m | done (GPU1 released) |
| tg-sweep r160 (21 T) | 27126332 (GPU2, label PS3_tg160) | 21:05 | ~22:15 | ~1h 10m | done (GPU2 released) |
| tg-sweep r400 (21 T) | b9aa1b40 (GPU3, label PS3_tg400) | 21:05 | 21:56 | 0h 51m | done (GPU3 released) |
| murnaghan BM (5 P)   | 4bd31b6f (GPU2, label PS3_murn) | 22:32 | 00:04 | 1h 32m | done (GPU2 released) |

GPU inventory (`nvidia-smi` at run start): GPU 1: NVIDIA A800 40GB Active, 40 GB, 39.85 GB free (claim label PS3)

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=299.78 K · 1951 frames (skip=50) · 2026-06-23 20:46 · **Overall: PASS**

**A. Thermo:** density drift 0.0022% (p=0.96) PASS · energy drift 0.0161% PASS · density block-SEM 0.0296% PASS · energy block-SEM 0.0116% PASS
**B. Chain conf:** Rg CV 12.0% PASS · MSID slope 0.994 (R²=0.993) OK · C(t) τ_relax 264166.6 ps (10% decayed) ⚠ partial · MSD no kinetic trap (α=0.22) OK · R_ee 29.74±11.09 Å (N=10)
**C. Packing:** P2 nematic 0.0173±0.0062 (<0.10) PASS · density homogeneity CV 24.8% (<25%) PASS
**Warnings:** C(t) partially decayed (10% at end, τ_relax 264 ms >> T_traj 1.95 ns) — ADVISORY ONLY for glassy PS; structural gates all PASS. Under-equilibration caveat: Tg may be over-estimated, K may run low (consistent with prior PSTR/PCFF memory).

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | CV 12.0% | CV < 30% → PASS |
| MSD plateau   | still diffusing (α=0.22, no kinetic trap) | PASS (advisory) |
| Density homog (CV) | 24.8% | < 25% → PASS |
| C(t) decay (melt NVT) | 10.3% at end (τ=264166.6 ps) | advisory (glassy carve-out) |
| τ_c chain relax (KWW) | 264166.6 ps | annotation only |
| R_ee mean ± std | 29.74 ± 11.09 Å (N=10 chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 0.988 ± 0.0003 g/cm³ | 0.997–1.103 (exp 1.05) | −5.9% | NPT 300K plateau | ⚠ (within ±10%, outside ±5%) |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (reported) | 376.5 K   | 373–383 K              | +0.9% | MD @40 K/ns (slowest); VF Γ→0=375.5 K corroborates | ✓ |
| Tg (DSC log-linear extrap) | 80 K (REJECTED) | — | — | log-linear over 11 decades, R²=0.67 — UNRELIABLE, not reported | ⚠ flagged |
| Tg (MD @400 K/ns) | 404.3 K | —                     | —    | bilinear, highest screening rate (high-rate saturation) | annotation |
| α_g (CTE) | 28.4×10⁻⁵ K⁻¹  | ~17–25×10⁻⁵ K⁻¹ (vol.) | high | cte_glassy (r160); volumetric | ⚠ slightly high |
| α_r (CTE) | 44.0×10⁻⁵ K⁻¹  | ~55–60×10⁻⁵ K⁻¹ (vol.) | —    | cte_rubbery (r160); α_r/α_g=1.55 | ⚠ |
| ΔCp at Tg | 0.0166 J/(g·K) (r160) | ~0.26–0.30 J/(g·K) | low | H(T) bilinear fit (r160); MD underestimates ΔCp | ⚠ |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 2.53 ± 0.11 GPa | 3.3–4.0 GPa    | −23% | murnaghan (5-point EOS @300 K; B_dyn diag 2.86 GPa) | ⚠ underpredict (PCFF/PSTR systematic) |
| B0' | 13.57  | 7–11 (typical) | —    | Murnaghan fit (∈[4,20] accept band)     | annotation |
| G   | N/A | — | — | not computed (Murnaghan path; no deform) | N/A |
| E   | N/A | — | — | not computed (Murnaghan path; no deform) | N/A |

Simulation dir: `data/PS3/lammps/`
Outputs: `data/PS3/raw/` — JSONs; `data/PS3/graphs/` — PNGs; `data/PS3/raw/run_summary.json`

---

## OVERALL VERDICT

| Property | Value | Exp | Status |
|----------|-------|-----|--------|
| **Tg** | 376.5 K | 353–393 K (lit. 373–383) | ✅ PASS (+0.9% vs lit. lower) |
| **Density (300 K)** | 0.988 g/cm³ | 0.997–1.103 (mid 1.05) | ⚠ marginal (−0.9% vs exp lower bound; −5.9% vs 1.05) |
| **Bulk modulus** | 2.53 ± 0.11 GPa | 3.3–4.0 GPa | ⚠ underpredict (−23%, known PCFF/PSTR systematic) |

**Headline:** Tg is the standout result — 376.5 K lands squarely on experiment, and uniquely for this PSTR/PCFF system the multirate slope was physically correct (slope_gate PASS), unlike the prior inversion failures. Density is marginally below the experimental band; K underpredicts by the documented PCFF/PSTR margin (prior PS2: 2.44 GPa). The DSC log-linear extrapolation was rejected (R²=0.67, 1-decade rate span) and the slowest-rate MD Tg reported instead, corroborated by the VF Γ→0 limit (375.5 K).

run_summary.json: `data/PS3/raw/run_summary.json` (run_id 5132ae42)

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 14.4 h  |  **GPU**: 14.4 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PS3/lammps/**/*.log` (Born stages excluded); reproducible via `manuscript/gen_table_compute_cost.py`.
