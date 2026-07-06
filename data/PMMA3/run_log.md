# Atactic Polymethyl Methacrylate (PMMA) Run 3 · 2026-06-24 → 2026-06-26
<!-- Run summary: data/PMMA3/raw/run_summary.json | Overall: Tg PASS; density + K FAIL (consistent PCFF bias). Tg 379 K (0.0% vs 378.1–380.1, EXCELLENT); density 1.117 g/cm³ (−4.6% vs 1.17–1.188); K 5.005 GPa (+19.2% vs K_T 3.5–4.2, Mark2007). K graded vs isothermal K_T (MD Murnaghan = K_T), NOT the K_S-inflated DB band [4.082,5.1]. Total wall ~36 h (equil ~19 h under 3-pipeline contention). 1 recovery (R1: equil pack-overlap → rebuild seed 555781). Tg scope: single-rate 100 K/ns (budget), no DSC extrapolation. -->

SMILES: `*CC(C)(C(=O)OC)*`  |  FF: PCFF  |  Charges: bond-increment (embedded)  |  DP: 50  |  Chains: 10  |  GPU: 3
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=555781 (rebuild; 555780 failed — see R1)  |  SEED_HOT=800168  |  SEED_COLD=453530
Plan: `data/PMMA3/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved (round 1, 0 findings)  |  T_workflow_K: 550

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                | classify_polymer → PACR → EMC PCFF (Class II) auto-routed |
| D-02 Charges        | bond-increment (embedded in PCFF)        | EMC class-II FF: bond-increment charges embedded, no QM step |
| D-03 Electrostatics | PPPM, 12 Å                          | ester C=O / O heteroatoms → long-range Coulomb |
| D-04 System size    | DP=50, 10 chains, 7520 atoms                        | polymer_rules.json PACR default (EMC seed 555780) |
| D-05 Convergence    | PASS                         | Thermo converged (density drift 0.14%, energy drift 0.04%, block-SEM 0.02%); P2=0.016, Rg CV 19.2%. Only failing structural check was melt-homogeneity CV 28.7%>25% — a 550 K melt-dump artifact a 300 K cell can't change → require_glassy carve-out → PASS. Density 1.1166 g/cm³ (SEM 0.0002), ~-6% vs PMMA exp 1.19 (known PCFF/PACR bias). |
| D-06 Tg fit quality | EXCELLENT  | R²=0.9976, bilinear knee; is_glassy=true (Tg=379 K > 300 K). Single-rate MD @ 100 K/ns: Tg=379.0 K (alt 379.3 K, clean transition) vs exp 378 K (+0.3%). Note: single-rate (no DSC extrapolation) — the rate-overestimate and PCFF underestimate evidently cancel here. α_g=1.79e-4/K, α_r=2.50e-4/K, ΔCp=0.083 J/g/K. |
| D-06b Multirate Tg  | N/A — single-rate (budget-scoped)                              | **Scope decision (user-approved):** equil consumed ~19.5 h under heavy 3-pipeline contention; full 3-rate multirate sweep (25/50/100 K/ns ≈ 32 M steps ≈ 47–69 h on this cell at 89–188 ts/s) cannot fit the 48 h cap. Ran SINGLE highest rate (100 K/ns) only. Tg reported as a rate-limited MD value — overestimates true Tg vs DSC; no log-linear extrapolation. |
| D-07 Property method | murnaghan (glassy, 300 K, ±1000 atm) | is_glassy=true (PMMA Tg~378 K). K=5.005±0.073 GPa, B0′=13.11 (∈[4,20]), r²=0.9996, all 5 P-points volume-equilibrated. Fluctuation cross-check 5.37±0.19 GPa (consistent). Accepted; above exp [3.5,4.2] = known PCFF/PACR ~+20% stiffness bias (not a fit failure). |

<!-- Example — PS1 completed run:
| D-01 | PCFF | classify_polymer returned PSTR → EMC PCFF auto-routed |
| D-02 | bond-increment | PCFF: bond-increment charges embedded, no QM step |
| D-03 | pppm 12 Å | Aromatic ring partial charges → long-range Coulomb |
| D-04 | DP=40, 10 chains, ~6400 atoms | polymer_rules.json default |
| D-05 | PASS | density drift 0.4% over last 500 ps; energy plateau confirmed |
| D-06 | ACCEPTABLE | R²=0.93, F-stat GOOD, N=19 bins; range 550→250K in 20K steps |
-->

<!-- Add rows for any non-routine decisions (parameter overrides, custom protocols, etc.) -->

| D-08 Hardware | engine=kokkos, mpi=1, gpu_per_run=1 (GPU 3) | policy-derived from hardware_policy[pcff] (no plan override); KOKKOS TURING75 binary. GPU 3 claimed in ledger (label `PMMA3`) despite co-tenant ML job (~10 GB) — task pins GPU 3. |

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts) -->

### R1 — Equil chain failed at nvt_softheat (PPPM out-of-range), attempt 1
- **Symptom:** Equil chain `4b5494b0` (EMC seed 555780) failed ~1 min after submit. minimize stage completed; chain died at stage 2 `nvt_softheat` between step 0→1 with `ERROR on proc 0: Out of range atoms - cannot compute PPPM` (KOKKOS pppm_kokkos.cpp:1150).
- **Root cause:** EMC pack had a localized severe atomic overlap that minimization (lj/class2 soft 9-6 core) left unresolved; NVT heating 300→630 K slingshots that atom out of the PPPM grid in the first timestep. Initial Press +4864 atm, E_vdwl +1875 (repulsive overlaps present).
- **Evidence it's pack-specific, not protocol:** PMMA2 ran the IDENTICAL deck (lj/class2/coul/long, pppm 1e-6, neighbor 2.0, dt 0.5, nvt 300→630 @ 50 damp) with a HIGHER step-0 pressure (8159 atm) and survived (relaxed to ~600 atm by step 1000). Only the EMC packing seed differs.
- **Fix (attempt 1):** Rebuild cell with a fresh EMC seed (555781; new pack avoids the overlap; stays within validated protocol — no deck surgery), then re-run equil. **Outcome: converged** — new chain `bd435bce` cleared nvt_softheat (advanced to step 7000+, pressure relaxed to ~−700 atm; prior pack died at step 0→1). Confirms root cause was a localized pack overlap specific to seed 555780, not the protocol.

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (seed 555780) | 4b5494b0 | 22:45 | 22:46 | ~1m | failed (nvt_softheat PPPM out-of-range — see R1) |
| equil (seed 555781) | bd435bce | 23:01 | 17:58 (+1d) | ~19h (heavy 3-pipeline contention) | done — 9/9 stages, status completed |
| murnaghan (5×P, ±1000 atm, 300K) | d869ed9a | 18:20 (+1d) | ~01:30 (+2d) | ~7h (heavy contention) | done — 5/5 points, status completed |
| tg-sweep r100 (600→150K, 20K step, 100 K/ns) | 0b5b294c | ~02:00 (+2d) | ~10:00 (+2d) | ~8h | done — 24/24 temps, status completed (vel seed 659164) |

GPU inventory (`nvidia-smi` at run start): GPU 3: RTX 6000, 24 GB, ~14 GB free (co-tenant ML job ~10 GB, no PolyJarvis run). Concurrent sessions: PLA3 (GPU1), PEEK3 (GPU2).

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=300.04 K · 1951 frames (skip=50) · 2026-06-25 18:00 · full block: `data/PMMA3/raw/d05_block.md`

**Overall: PASS** (density-homogeneity CV failure = 550 K melt-state artifact; require_glassy carve-out applied)

| Section | Check | Value | Threshold | Result |
|---------|-------|-------|-----------|--------|
| A Thermo | Density drift | 0.143% (p=0.0) | <1% | PASS |
| A Thermo | Energy drift | 0.0445% (p=0.224) | <1% | PASS |
| A Thermo | Density block-SEM | 0.0205% | <1% | PASS |
| B Chain | Rg CV (chain–chain) | 19.2% | <30% | PASS |
| B Chain | MSID slope | 1.043 (R²=0.993) | 1.0±20% | OK |
| B Chain | C(t) τ_relax | 2.93e9 ps (3% decayed) | — | ⚠ advisory (glassy) |
| B Chain | MSD kinetic trap | no (α=0.181) | — | OK |
| C Spatial | P2 nematic order | 0.0163±0.004 | <0.10 | PASS |
| C Spatial | Density homogeneity CV | 28.7% (7³ grid, 21.9 atoms/voxel) | <25% | FAIL → carve-out (melt artifact) |

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg CV (chain–chain) | 19.2% | CV < 30% → PASS |
| MSD plateau   | not trapped (α=0.181, MSD 320.8 Å² >> Rg² 211.7) | OK |
| Density homog (CV) | 28.7% | < 25% → FAIL → melt-artifact carve-out (PASS) |
| C(t) decay (melt NVT) | 2.9% at threshold 0.1 (advisory; glassy carve-out) | advisory |
| τ_c chain relax (KWW) | 2.93e9 ps | annotation only |
| R_ee mean ± std | 29.93 ± 14.5 Å (N=10 chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.1166 ± 0.0002 g/cm³ | 1.170–1.188 (DB, exp-lookup) | −4.6% | NPT 300K plateau | ✗ FAIL (known PCFF/PACR density bias) |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (MD @100 K/ns, single-rate) | 379.0 K | 378.1–380.1 K | 0.0% | bilinear density(T) knee, R²=0.9976 | ✓ |
| Tg note | single-rate (budget-scoped) | — | — | NO DSC extrapolation; rate-overestimate & PCFF underestimate cancel here (±1 K of exp) | annotation |
| α_g (CTE) | 17.9×10⁻⁵ K⁻¹ | — | — | −a_glassy / ρ_mean_glassy | annotation (no exp ref in DB) |
| α_r (CTE) | 25.0×10⁻⁵ K⁻¹ | — | — | −a_rubbery / ρ_mean_rubbery (α_r>α_g ✓) | annotation |
| ΔCp at Tg | 0.083 J/(g·K)   | — | — | H(T) bilinear fit         | annotation |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 5.005 ± 0.073 GPa | 3.5–4.2 GPa (K_T isothermal, Mark2007) | +19.2% | murnaghan (±1000 atm, 300 K, r²=0.9996) | ✗ FAIL (known PCFF/PACR stiffness bias) |
| K grading note | — | — | — | — | MD Murnaghan computes K_T (isothermal); graded against the K_T range [3.5,4.2]. The exp-lookup DB range [4.082,5.1] includes ultrasonic K_S (> K_T) and would have shown a misleading "within-range PASS" — NOT used for the grade (K_T-vs-K_S apples-to-oranges). Fluctuation cross-check 5.37 GPa confirms K is genuinely high. |
| B0' | 13.11   | 7–11 (typical) | —    | Murnaghan fit (within accepted [4,20])  | annotation |
| G   | N/A | — | — | not computed (deform fallback not triggered — Murnaghan fit converged) | N/A |
| E   | N/A | — | — | not computed (deform fallback not triggered) | N/A |

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 31.4 h  |  **GPU**: 31.4 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PMMA3/lammps/**/*.log` (Born stages excluded); reproducible via `paper/gen_table_compute_cost.py`.
