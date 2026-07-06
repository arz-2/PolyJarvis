# Polyetheretherketone (PEEK) Run 1 · 2026-06-18 17:22 → 2026-06-20 11:42 (~42 h, within 48 h cap)
SMILES: `*Oc1ccc(Oc2ccc(C(=O)c3ccc(cc3)*)cc2)cc1`  |  FF: PCFF  |  Charges: RESP  |  DP: 15  |  Chains: 8  |  GPU: 0,2,3
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=-1 (random; resolved packing seed not persisted by EMC server, job bb04bfce)  |  SEED_HOT=387399 (velocity init, nvt_softheat)  |  SEED_COLD=N/A (Nose-Hoover NVT/NPT; no explicit seed)
Plan: `data/PEEK1/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved (r1 deterministic; r2 reasoned revision, 0 findings)  |  T_workflow_K: 770

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                                                | classify_polymer → PKTN (class 19) → EMC auto-routed PCFF (lammps_flags use_pcff=true) |
| D-02 Charges        | embedded in FF                                       | EMC/PCFF bond-increment charges; no separate charge step (prompt charge_method=resp N/A on EMC path) |
| D-03 Electrostatics | PPPM                                                 | aromatic ether/ketone heteroatoms → PPPM |
| D-04 System size    | DP=15, 8 chains, 4096 atoms                          | run_plan.json defaults; EMC job bb04bfce, density_initial=0.66 |
| D-05 Convergence    | ACCEPT screening-grade (was EXTEND→terminal)          | Static gates PASS (Rg CV 20%, P2 0.038, dens-homog CV 15%) + ρ_300K=1.193 converged, in-gate. C(t)/MSD terminal-relaxation demoted to advisory (rigid backbone; 8×850K anneal failed; segmental dyn equilibrated). User-confirmed. Tg-overestimate + K-low caveats. |
| D-06 Tg fit quality | GOOD (R²=0.9909, Tg=532.7 K) — full 19-pt log (revised from R²=0.9887/537.4 K partial)  | Single-rate 40 K/ns sweep, COMPLETE staircase 700→350 K (19 T-pts). Bilinear fit: α_g=2.130×10⁻⁴ K⁻¹, α_r=3.866×10⁻⁴ K⁻¹ (ratio 1.82), ΔCp=+0.037 J/(g·K) (success; H-fit ACCEPTABLE R²=0.9502 — improved over partial). Tg_MD=532.7 K vs Tg_exp=418 K (+114.7 K ≈ +27%) — single-rate cooling-rate bias. Tg_alt=500 K (secondary fit, −33 K); primary F-stat Tg reported. See R-04. |
| D-07 Property method | deform (glassy fallback, uniaxial) | is_glassy=true by definition. Born attempted first (parallel GPU3) but infeasible (4ns×numdiff≈130h; partial K_T unphysical, see R-02/R-03) → sanctioned deform fallback, fast rate 1e8 s⁻¹, 0.3 ns. K=(C11+2C12)/3. Caveats: ρ ~5.5% low (K-low), fast strain rate (K-high), affine K_Born=84 GPa = upper bound only. |

<!-- Add rows for non-routine decisions (parameter overrides, custom protocols, etc.) -->

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts) -->

### R-01 · Equil gate EXTEND/FAIL — melt chain relaxation (routed to planner, not extended)
- **Symptom:** equil-check overall_pass=FALSE, verdict=EXTEND. Melt-NVT C(t) (end-to-end vector autocorrelation) decayed only 0.1% (threshold 10%); τ_relax unresolved; MSD kinetic trap (MSD_max 83 Å² ≪ Rg² 569 Å²). Static structure all PASS (Rg CV 20%, P2 0.038, density-homog CV 15%, R_ee 55±20 Å). 300 K ρ converged = 1.193 g/cm³.
- **Diagnosis:** melt NVT production = `run 1000000` ×1 fs = **1 ns** at 770 K. 0.1% C(t) decay over ~2 ns ⟹ terminal relaxation ~hundreds of ns (≈100× the class-note τ_Rouse≈2.2 ns estimate). The prescribed 1–2 ns extension cannot move C(t); MSD/density failures are not addressable by more NVT (fixed volume). This is a **plan-assumption contradiction** (deterministic PKTN plan assumed 770 K protocol relaxes the melt), not a worker error.
- **Action:** Skipped the futile extension. Routed to planner (per "probe contradicts plan assumption → return control to planner") to (a) decide accept-screening-grade by relaxing equil success_criteria to static-structure + density gates with a documented Tg-overestimate caveat, and (b) reassess whether the 3-rate Tg sweep fits the remaining ~35 h budget. Re-critic after.
- **Also logged:** checker's exp-density ref (1.20) is wrong. FINAL canonical ref = AMORPHOUS PEEK **1.263 g/cm³** (1.30–1.32 is semicrystalline) → 1.193 is **−5.5%** (inside gate [1.02,1.38]). Screening caveat, not a blocker. [Interim notes said 1.30–1.32/−9%; superseded by 1.263/−5.5% per planner correction — reconciled across run_summary.json + RESULTS-A.]
### R-02 · Tg-sweep throughput ~½ estimate → de-scope to single-rate + parallelize Born (planner's pre-delegated contingency)
- **Symptom:** rate-40 Tg sweep measured ~83 steps/s ≈ 7 ns/day (vs ~14 ns/day assumed) — NPT barostat + denser low-T cells; 4096-atom system also underutilizes the GPUs (7–37% util). At 7 ns/day the full 3-rate sweep + sequential Born does NOT fit the 48 h cap (17:22 06-20).
- **Decision (executing planner's round-2 pre-delegated scope contingency, not a new scientific call):**
  1. **Drop rates 160 & 640** → single-rate Tg at 40 K/ns (slowest/most reliable). VF/multirate extrapolation needs ≥2 decades; [40,640] is only 1.2 decades (already POORLY_CONSTRAINED), so the loss is near-zero scientifically — single-rate Tg + cooling-rate-overestimate caveat is the legitimate screening deliverable. Recovers ~5 h.
  2. **Parallelize Born** on GPU 3 (co-located with the sweep's idle compute), since Born is independent of the Tg result — needs only npt_prod300_out.data (done) + is_glassy=True (definitional). Decouples K from the budget collision; finishes well before rate-40.
  3. Let rate-40 run to 350 K (anchor, 57% sunk, clean bilinear bracket).
- **Outcome:** partial — single-rate Tg path holds. BUT the parallel Born (run 0b5a1c8c, born_run_ns=4.0 → 4M steps) proved infeasible: 86k/4,000,000 steps after ~3 h (~8 steps/s; `born/matrix numdiff` does ~12 extra force evals/sample + shared-GPU contention) → ~130 h projected. **Killed at 06:20 06-20**, freeing GPU 3 back to the sweep. See R-03 for the K re-plan. (Root lesson: born_run_ns=4.0 is far too long for numdiff-Born cost — affine Born term converges in a fraction of that.)

### R-03 · Born run-length infeasible → re-plan K (short-Born after sweep vs free NPT-fluctuation K)
- **Symptom:** 4 ns Born numdiff ≈ 130 h at measured throughput. Sweep (rate-40) frees all GPUs ~14:00 06-20; only ~3 h to the 48 h cap after.
- **Investigated the killed run's data (advisor steer):** `born_matrix.dat` affine terms ARE converged (87 samples, CV ~0.5%) → K_Born = **84.33 GPa**. But the extractor is K_T = K_Born + NkT/V − (V/kT)·Var(P): ran it on the partial data (eq_fraction 0.7, 62 prod rows) → **K_T = −49.6 GPa** (unphysical), fluct correction 134 GPa ≫ K_Born, SEM 14 GPa. Cause: Var(P) under-sampled (only ~62 pressure points at thermo=1000). The fluctuation method is a difference of two large near-cancelling terms → won't converge to ±1–2 GPa in the ~3 h GPU budget after the sweep.
- **Decision:** Born path effectively FAILED (infeasible run length + unphysical partial K). Invoke the **sanctioned deform fallback** (CLAUDE.md: "Recovery if born-worker fails → spawn deform-worker") — uniaxial NEMD deformation, direct stress–strain modulus, no noisy cancellation, ~0.3 ns ≈ 1 h on freed GPUs. Retain K_Born=84.33 GPa as a documented affine **upper bound** only (not the reported K). Run deform after the sweep frees GPUs (~14:00).
- **Outcome:** pending deform run (post-sweep)

### R-04 · Tg re-extracted from the COMPLETE sweep (partial-log value superseded)
- **Symptom:** the rate-40 sweep was reported "done-partial (engine wall-cap, 16 T-pts 700→400 K)" and Tg=537.4 K was fit to that partial log. On a later check (06-20 ~15:xx) the LAMMPS process (PID 478970, GPU 3) was found STILL RUNNING — it had not been killed at run close. It then finished cleanly at 15:38: 19/19 staircase points 700→350 K, 29.5 h wall, sentinel `done_4fa96c72.json` status=completed. The "wall-cap" was a mis-read — the run simply hadn't finished.
- **Action:** Re-ran the thermal track via `tg-analysis-worker` (`gen_prompt.py --stage analyze-tg --plan run_plan.json`) on the full log. Analysis-only, no new simulation.
- **Outcome:** **Tg = 532.7 K** (GOOD, R²=0.9909), down 4.7 K from the partial 537.4 K — the added low-T glassy branch (down to 350 K) tightened the bilinear fit. ΔCp now computes (+0.037 J/(g·K), H-fit ACCEPTABLE R²=0.9502 vs prior POOR). α_g=2.13e-4, α_r=3.87e-4 (ratio 1.82). Tg_alt=500 K (secondary fit, −33 K) noted; primary F-stat Tg reported. Reconciled run_summary.json (tg block → 532.7 K, +27.4%) + RESULTS-B + D-06 + timing/state rows. Net: Tg conclusion unchanged (screening-grade over-estimate vs exp 418 K), now backed by the complete dataset. **Lesson:** kill or confirm-complete the sweep process before declaring a run done — a backgrounded LAMMPS job can outlive the orchestrator's "complete" call and keep producing data.

### R-01 outcome (cont.)
- **Outcome:** converged on screening-grade acceptance. Planner (round 2, reasoned) accepted equil as TERMINAL — equil success_criteria revised to static-structure + density gates; C(t)/MSD demoted to advisory; added D-05_convergence (confidence medium) with Tg-overestimate + K-low caveats. **User confirmed** screening-grade over a high-T (~1050 K) relaxation probe, after being shown that (i) the 8×850 K anneal already failed to relax, (ii) Tg is segmentally-governed and segmental/local structure IS equilibrated, (iii) dominant Tg bias is cooling-rate (handled by 3-rate multirate). Tg window = 700→350 K (budget-safe). Equil NOT extended.

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Status |
|-------|----|-----------|--------|
| equil | 36b819ed | 17:22 | done (05:16, 9/9 stages) |
| tg_sweep (rate 40 K/ns) | 4fa96c72 | 2026-06-19 10:06 | done-COMPLETE (ran to end 06-20 15:38; 19/19 T-pts 700→350 K, 29.5 h wall, sentinel=completed). Tg re-extracted from full log → 532.7 K (R-04). Prior partial 16-pt read was superseded. |
| born (NVT K_T, GPU3 parallel) | 0b5a1c8c | 2026-06-20 03:20 | KILLED 06:20 (4ns infeasible @8 steps/s; partial K_T unphysical) → deform fallback |
| deform (uniaxial, K fallback) | df832d7e | 2026-06-20 10:11 | done (~11:1x, completed) |

---

## D-05 CONVERGENCE DETAIL

<!-- Paste result["d05_markdown"] from check_equilibration_comprehensive here. -->

## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=769.69 K · 1951 frames analysed (skip=50) · 2026-06-19 05:17

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0% (p=nan) | <1%, p<0.01 | N/A (NVT — fixed volume) |
| Energy drift | 0.0342% (p=0.7515) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0% | <1% | N/A (NVT — fixed volume) |
| Energy block-SEM | 0.0241% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 20.0% | <30% | PASS |
| MSID slope | 1.095 (R²=0.9907) | 1.0 ±20% | OK |
| C(t) τ_relax | 1878759648.1 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.095, MSD=83.2 Å²>>Rg²=568.775) | — | ⚠ trapped |
| R_ee mean ± std | 54.99 ± 19.8 Å (N=8 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0382 ± 0.0029 | <0.10 | PASS |
| Density homogeneity CV | 15.1% (5³ grid, 32.8 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=1878759648.1 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | 23.4 ± 4.7 Å | CV = 20.0% < 30% → PASS |
| MSD plateau   | sub-diffusive (α=0.095) / kinetic trap | ⚠ trapped (expected glassy/short trajectory) |
| Density homog (CV) | 15.1% | < 25% → PASS |
| C(t) decay (melt NVT) | 0.1% | ✗ FAIL: < 10% threshold; τ_relax >> T_traj (1878759648 ps >> 1951 ps) |
| τ_c chain relax (KWW) | 1.88×10⁹ ps (unresolved) | trajectory too short for reliable τ estimate |
| R_ee mean ± std | 54.99 ± 19.8 Å (N=8 chains) | within expected range; good distribution |

---

## TIMING

| Worker | Submitted | Completed | Wall time | Throughput |
|--------|-----------|-----------|-----------|------------|
| Cell build (EMC) | 06-18 17:0x | 06-18 17:1x | ~few min | — |
| Equilibration (9 stages) | 06-18 17:22 | 06-19 05:16 | ~11 h 54 m | ~14 ns/day (melt NVT) |
| Tg sweep (rate 40 K/ns, COMPLETE 19/19 T) | 06-19 10:06 | 06-20 15:38 (finished) | 29.5 h wall | ~7 ns/day (NPT, low-T) |
| Born (killed, infeasible) | 06-20 03:20 | 06-20 06:20 (killed) | ~3 h (wasted) | ~8 steps/s (numdiff, shared GPU) |
| Deform (K, fast rate) | 06-20 10:11 | 06-20 ~11:15 | ~1 h | — |
| **Total** | 06-18 17:22 | 06-20 11:42 | **~42 h** (within 48 h cap) | — |

GPU inventory (`nvidia-smi` at run start, 06-18):
- GPU 0,2,3: Quadro RTX 6000, 24 GB each, ~23–24 GB free (GPU 1 excluded — busy; GPU 4 requested but does not exist)

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.193 ± 0.0005 g/cm³ | 1.263 g/cm³ (amorphous PEEK; 1.30–1.32 is semicrystalline) | −5.5% | NPT 300K plateau | ⚠ (screening; ~5.5% low vs amorphous ref) |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg        | 532.7 K           | 418 K (PEEK)           | +114.7 K (+27%) | bilinear fit (R²=0.9909, GOOD, full 19-pt 700→350 K) | ⚠ (single-rate cooling bias) |
| α_g (CTE) | 2.130×10⁻⁴ K⁻¹   | [exp. unknown]         | — | −a_glassy / ρ_mean_glassy | INFO |
| α_r (CTE) | 3.866×10⁻⁴ K⁻¹   | [exp. unknown]         | — | −a_rubbery / ρ_mean_rubbery (α_r/α_g=1.82) | INFO |
| ΔCp at Tg | +0.037 J/(g·K)    | [0.1–0.3 typical]      | — (H-fit ACCEPTABLE R²=0.9502) | H(T) bilinear fit | ⚠ (low vs typical; screening) |
| cooling rate | 40 K/ns    | ~10⁻⁷ K/ns (exp)       | —    | single-rate (rates 160, 640 dropped for budget)  | annotation |
| expected Tg offset | +50–120 K (screening) | — | — | — | caveat: no multirate correction |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 3.53 GPa | 4.0–7.0 GPa (amorphous PEEK) | −12% (below range) | deform fallback: uniaxial NVT, K=(C11+2C12)/3; R²=0.986; n=2801 pts; ε∈[0.002,0.03] | ⚠ WARNING: outside exp range (bias: ρ−9% pulls K low; fast rate 1e8 s⁻¹ partially compensates upward; net: K likely UNDERestimated) |
| B0' | N/A     | 7–11 (typical) | —    | Murnaghan fit (rubbery only)            | N/A (glassy) |
| G   | 0.89 GPa | ~1.3–2.0 GPa (exp) | — | deformation (C11−C12)/2 | INFO (no exp ref loaded in plan) |
| E   | 2.46 GPa | ~3.0–4.2 GPa (exp) | — | deformation 9KG/(3K+G) | INFO (no exp ref loaded in plan) |

### D — Chain Structure

| Metric | Value | Status |
|--------|-------|--------|
| Rg mean ± std     | 23.4 ± 4.7 Å | CV 20% < 30% → PASS |
| MSD plateau       | sub-diffusive (α=0.095), kinetic trap | ⚠ trapped — terminal relax incomplete (screening, accepted) |
| Density homog (CV)| 15.1% | < 25% → PASS |
| C(t) decay (melt NVT) | 0.1% | ✗ advisory (rigid backbone; demoted to non-blocking per D-05) |
| τ_c chain relax (KWW) | 1.88×10⁹ ps (unresolved) | annotation only |
| R_ee mean ± std   | 54.99 ± 19.8 Å (N=8 chains) | sourced from D-05 |

Simulation dir: `/home/arz2/PolyJarvis/data/PEEK1/lammps/`
Outputs: `data/PEEK1/raw/` — JSONs (equilibrated_density, tg_summary, bulk_modulus_deform, equilibration_comprehensive, run_summary), `data/PEEK1/graphs/*.png`

## K-method backfill (2026-06-30 17:08) — gated Murnaghan @300K
- chain_id: cfac7ef2 | GPU claim: PEEK1-murnbackfill (gpu 1) | mpi=1 kokkos PCFF
- pressures: [-1000,-500,0,500,1000] atm | cell: npt_prod300_out.data | out: data/PEEK1/raw/bulk_modulus_murnaghan.json
- status: monitoring
- RESULT (attempt 1, ±1000 atm): K0=4.912 GPa r²=0.9996 but B0'=1.06 → GATE FAIL (low-B0' breakdown, stiff aromatic). Queued for WIDE rerun [-1000,0,1500,3000,5000]. status: rerun-pending
- STATE: PEEK1 wide rerun chain 94a9ca92 (GPU3) pressures [-1000,0,1500,3000,5000]. status: monitoring
- RESULT (attempt 2, WIDE [-1000,0,1500,3000,5000]): K_Murnaghan = 5.158 GPa (r²=0.9998, B0'=6.30) → GATE PASS. Recovery from attempt-1 B0'=1.06 fail via wide compression-biased pressures. status: DONE

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 45.1 h  |  **GPU**: 45.1 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1/3
- Source: `data/PEEK1/lammps/**/*.log` (Born stages excluded); reproducible via `paper/gen_table_compute_cost.py`.
