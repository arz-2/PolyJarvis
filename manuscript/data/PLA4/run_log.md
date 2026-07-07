# Polylactic Acid (PLA) Run PLA4 · 2026-06-26 → 2026-06-27
SMILES: `*C(C)C(=O)O*`  |  FF: PCFF  |  Charges: none (PCFF bond-increment)  |  DP: 50  |  Chains: 10  |  GPU: 0 (claimed via pick_gpu; task requested 3 but allocator handed free GPU 0)
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=481723  |  SEED_HOT=125625 (nvt_softheat velocity create)  |  SEED_COLD=125625 (single velocity-create chain)
Plan: `data/PLA4/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved (round 1, 0 findings)  |  T_workflow_K: 620

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF (EMC, KOKKOS engine, mpi=1)                    | classify_polymer → PEST → EMC PCFF auto-routed; PCFF has explicit ester types (c_1, o_2, oe) |
| D-02 Charges        | bond-increment (embedded in PCFF)                   | EMC Class-II FF: charges embedded, no QM step |
| D-03 Electrostatics | PPPM, 12 Å cutoff                                   | ester C=O dipole → long-range Coulomb required |
| D-04 System size    | DP=50, 10 chains, 4520 atoms                        | polymer_rules.json PEST default |
| D-08 Hardware       | engine=kokkos, gpu=0, mpi=1                          | hardware_policy[pcff] default; GPU claimed via pick_gpu (label PLA4) |
| D-05 Convergence    | PASS                                                 | overall_pass=true; all hard gates pass (density/energy drift, block-SEM, CV 23.6%, P2 0.018); C(t) advisory under glassy carve-out. Equil resumed after disk-full (R-01). |
| D-06 Tg fit quality | per-rate EXCELLENT, multirate ABORT (slope gate) | Per-rate fits EXCELLENT (R²≥0.995) but slope_gate FAIL (b<0). is_glassy=TRUE from exp_Tg=331K>300K (MD fit degenerate → exp-Tg routing). Best-estimate Tg=363.4K (r100). |
| D-06b Multirate Tg  | DSC-equiv=446.9 K DISCARDED (slope_gate FAIL)        | log-linear Tg(Γ) b=−77.7 K/ln, R²=0.74, N_rates=3 @ [40,80,100] K/ns, N_repl=1; wrong-sign (slow rates delocalize) → single_rate_fallback. VF FAILED (<1 decade). STRUCTURAL PEST failure, not rate/seed — recovery futile; corrected rates [40,80,100] still fail (vs PLA3 [25,50,100]). |
| D-07 Property method | murnaghan (glassy, ±5000 atm) | is_glassy=TRUE from plan exp_Tg=331 K > 300 K (no need to wait for thermal — PLA3 MD Tg=430 K + glassy 1.226 g/cm³ density corroborate). bm_pressures_atm=[-5000..5000] (PEST wide-range fix; ±1000 caused PLA3 B0'=30 reject). |
| D-09 Track order    | mechanical BEFORE thermal (deviation from MECHANICAL_TRACK gate) | Advisor-endorsed: bank K (survivable headline, per PLA3) before the long/fragile PEST thermal track; is_glassy unambiguous from exp_Tg so the "wait for thermal" gate premise (rubbery-at-300K risk) does not apply. |

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

### R-01 · equil chain npt_prod300 (stage 9/9) failed — disk full
- **Symptom:** Chain 267d7173 reached 8/9 stages, then npt_prod300 died at MD step 1,226,000 / 2,000,000.
  Log: `ERROR on proc 0: Error writing dump dump_npt: No space left on device (src/dump.cpp:543)` → MPI_ABORT.
- **Root cause:** Root partition `/dev/nvme0n1p2` (937G) at 100% (0 B free). Pure I/O failure — physics
  was healthy at the crash (T≈300 K, density≈1.23 g/cm³, stable box). All stages 1–8 `_out.data` intact,
  incl. `npt_cool300_out.data` (the resume input).
- **Fix:** User freed disk (→50 G free). Removed only the failed stage's partials (403 MB partial dump +
  stale logs). Rebuilt npt_prod300 as `npt_prod300_resume.in` — identical params (read npt_cool300_out.data,
  NPT 300 K, 2M steps, write npt_prod300_out.data) but **trajectory dump removed** (not needed downstream;
  disk <60 G triggers dump-disable policy). Resubmitted as run 82d8c8b1 on GPU 0 (KOKKOS, mpi=1).
- **Outcome:** converged. Resume run 82d8c8b1 completed all 2M steps (final density≈1.231 g/cm³, T≈301 K), wrote npt_prod300_out.data (4520 atoms). Equil chain now fully complete (8 original stages + resumed stage 9).

### R-02 · Murnaghan BM cavitated at −5000 atm tension (attempt 1/2)
- **Symptom:** Chain db40275f failed at the FIRST point bm_P−5000. Cell exploded by step 10,800:
  T→22,530 K, volume 4.8e4→1.2e8 Å³, density→0.0005 g/cm³. Log: `Out of range atoms - cannot compute
  PPPM` (preceded by `Shake determinant < 0.0` — a consequence, not cause).
- **Root cause:** ±5000 atm SYMMETRIC range (polymer_rules PEST fix) is fatal on the TENSION side
  for a glassy cell — −5000/−2500 atm tension cavitates it. The ±5000 fix was motivated by the
  COMPRESSION-side B0' runaway (PLA3 B0'=30 at ±1000); it overlooked tension cavitation.
- **Fix:** Compression-biased range [−1000, 0, 1500, 3000, 5000] — mild tension (−1000 atm ran
  stably in PLA3) + strong compression to +5000 atm for EOS curvature to constrain B0'. Re-submitted.
- **Outcome:** converged. Recovery run 48ebb79a completed all 5 points cleanly (no cavitation, no errors).
  Densities monotonic: P=−1000→1.206, P=0→1.231, P=1500→1.264, P=3000→1.286, P=5000→1.316 g/cm³.
  Compression-biased range solved both the tension cavitation (vs symmetric ±5000) and the curvature
  deficit (vs ±1000). BM extraction pending.

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage) | 267d7173 | 10:50 | 16:11 (stages 1–8 only) | ~5h | failed @ npt_prod300 (disk full) |
| equil resume (npt_prod300) | 82d8c8b1 | 16:35 | 18:39 | ~2h | done |
| murnaghan BM (5×±5000atm) | db40275f | 18:55 | 19:05 | ~10min | failed @ bm_P-5000 (cavitation) |
| murnaghan BM (5×[-1000..5000]) | 48ebb79a | 19:08 | 21:55 | ~2h47m | done → K=5.14 GPa (B0'=7.92, r²=0.99998); GPU 0 released |
| tg-sweep r40 (26 T, 600→100K) | 505af61a | 19:14 | ~08:15 | ~13h | done → Tg=446.9K (R²=0.9974 EXCELLENT, 24.9K gap); GPU 3 released [seed 149514] |
| tg-sweep r80 (26 T, 600→100K) | bb68d578 | 22:05 | 04:30 | ~6.4h | done → Tg=423K (R²=0.9951 EXCELLENT, 45K delocalized) [GPU 0, seed 389109] |
| tg-sweep r100 (26 T, 600→100K) | ac9e597d | 04:35 | ~09:30 | ~5h | done (swept to 101K, no errors); GPU 0 released [seed 899034] |

GPU inventory: GPU 0 (claimed, label PLA4): Quadro RTX 6000 24GB. KOKKOS engine, mpi=1.
GPU 3 (claimed, label PLA4-thermal) added mid-run (user granted free GPU 3): thermal track runs in PARALLEL with mechanical to recover budget lost to disk-full. KOKKOS, mpi=1.

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=300.05 K · 951 frames analysed (skip=50) · 2026-06-26 18:44

**Overall: PASS (glassy carve-out applied)**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0227% (p=0.6253) | <1%, p<0.01 | PASS |
| Energy drift | 0.0093% (p=0.8421) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0285% | <1% | PASS |
| Energy block-SEM | 0.0097% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.4% | <30% | PASS |
| MSID slope | 1.172 (R²=0.9779) | 1.0 ±20% | OK |
| C(t) τ_relax | 45336.2 ps (7% decayed) | — | ⚠ ADVISORY |
| MSD kinetic trap | no (α=0.271, MSD=553.68 Å²>>Rg²=243.36) | — | OK |
| R_ee mean ± std | 34.46 ± 18.65 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0184 ± 0.0053 | <0.10 | PASS |
| Density homogeneity CV | 23.6% (6³ grid, 20.9 atoms/voxel) | <25% | PASS |

**Gate logic:** Hard gates (density/energy drift, block-SEM, CV, P2) all PASS. C(t) decay advisory (glassy is_glassy=true, DP=50≥30 exempts from C(t) hard gate). Verdict: PASS.

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg CV (chain–chain) | 21.4% | CV < 30% → PASS |
| MSD kinetic trap | no (α=0.271) | PASS |
| Density homog (CV) | 23.6% | < 25% → PASS |
| C(t) decay (melt NVT) | 7% at threshold 15% | ⚠ advisory (glassy carve-out) |
| τ_c chain relax (KWW) | 45336.2 ps | annotation only |
| R_ee mean ± std | 34.46 ± 18.65 Å (N=10 chains) | INFO |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.226 ± 0.0003 g/cm³ | ~1.25 g/cm³ (amorphous PLA) | within polymer_rules band [0.974–1.317] | NPT 300K plateau (9-stage equil, resumed) | ✓ |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (best-estimate, r100) | 363.4 K | 326–327 K (DB, high-conf) | +36 K raw (+11%); 0% vs +100K MD-offset band | bilinear fit, highest rate (single-rate fallback, slope_gate FAIL) | ✓ PASS (MD-offset grading) |
| Tg (DSC-equiv, INVALID) | 446.9 K (discarded) | — | — | log-linear Tg(Γ): b=−77.7 K wrong-sign, R²=0.74 — CONTAMINATED | ✗ discarded |
| α_g (CTE glassy) | 1.77×10⁻⁴ K⁻¹ | — | — | bilinear density-T fit (r100, cleanest) | INFO |
| α_r (CTE rubbery) | 3.59×10⁻⁴ K⁻¹ | — | — | bilinear density-T fit (r100) | INFO |
| ΔCp at Tg | 0.120 J/(g·K) | ~0.5 J/(g·K) lit. | — | H(T) bilinear fit (r100, R²=0.989) | INFO |

**Tg note:** Multirate slope gate FAILED (b=−77.7 K/ln, wrong sign; R²=0.74). Per-rate Tg: r40=446.9K (gap 24.9K), r80=423.0K (gap 45K), r100=363.4K (gap 2K, clean). Slow rates delocalize → invert the slope. This is STRUCTURAL for PLA/PEST (stiff ester backbone), NOT a rate or seed artifact — confirmed across PLA2 (r40=428.6K), PLA3 (slope-gate FAIL on [25,50,100]), and now PLA4 with the CORRECTED rates [40,80,100] still failing. Recovery re-run is futile (no cheap fix per THERMAL_TRACK PEST slope-fragility note) → pre-committed exp-Tg fallback. is_glassy=True from exp_Tg=331K>300K. Best-estimate Tg=363.4K from r100 (cleanest fit, no delocalization, closest to exp). Staged registry rows DISCARDED (contaminated; not committed to _tg_registry CSV).

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 5.142 ± 0.041 GPa | 3.0–4.5 GPa  | +14% above upper bound | Murnaghan EOS 300K, 5 pts [−1000,0,1500,3000,5000] atm (compression-biased after ±5000 cavitation) | ⚠ above exp (PCFF stiff-PEST bias) |
| B0' | 7.92   | 7–11 (typical) | —    | Murnaghan fit (r²=0.99998, gate PASS B0'∈[4,20]) | annotation |
| G   | N/A    | —              | —    | not extracted (Murnaghan primary; no deform run) | N/A |
| E   | N/A    | —              | —    | not extracted                            | N/A |

**K note:** Murnaghan accepted as primary glassy K (fit_converged=True, B0'=7.92∈[4,20], r²=0.99998 — clean). K=5.14 GPa is ~14% above exp upper bound (4.5), consistent with the documented PCFF overestimate for stiff PEST/acrylic classes (cf. PACR/PMMA ~15% high). Diagnostic fluctuation B_dyn=4.70 GPa corroborates the high side. (Cross-ref: PLA3 Murnaghan was rejected at ±1000 atm B0'=30 → deform fallback gave K=3.13 GPa; PLA4's wide-compression EOS is the higher-quality fit, hence the different headline value.)

**Overall: density ✓ PASS · Tg ✓ PASS (MD-offset) · K ✗ FAIL (+14.3%)**
All three properties extracted via valid methods. Density and Tg within grading tolerance. K=5.14 GPa is
+14.3% above exp [3.0–4.5] (no MD-offset allowance for mechanical props) → graded FAIL — the documented
PCFF stiff-PEST overestimate (cf. PACR/PMMA ~15% high), not a pipeline error; the Murnaghan fit itself is
high quality (B0'=7.92, r²=0.99998). Headline science: ρ=1.226 g/cm³, Tg≈363 K (r100, clean), K=5.14 GPa.
Recoveries: R-01 (equil disk-full → resumed), R-02 (Murnaghan tension cavitation → compression-biased range).
Thermal multirate slope-gate FAILED (structural PEST, not rate/seed) → r100 single-rate fallback.

Simulation dir: `data/PLA4/lammps/`
Outputs: `data/PLA4/raw/` — JSONs; `data/PLA4/graphs/` — PNGs; `data/PLA4/raw/run_summary.json`

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 33.4 h  |  **GPU**: 33.4 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PLA4/lammps/**/*.log` (Born stages excluded); reproducible via `manuscript/gen_table_compute_cost.py`.
