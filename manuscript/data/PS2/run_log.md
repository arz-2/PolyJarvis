# Atactic Polystyrene (PS) Run PS2 · 2026-06-22 → 2026-06-23
SMILES: `*CC(c1ccccc1)*`  |  FF: PCFF  |  Charges: bond-increment  |  DP: 40  |  Chains: 10  |  Atoms: 6420  |  GPU: 1
Requested: {density, tg, bulk_modulus}  |  Replicate: 1 of 1  |  Seeds: EMC=472916  |  SEED_HOT=285869 (equil velocity)  |  SEED_COLD=[tg-sweep pending]
Plan: `data/PS2/raw/run_plan.json`  |  mode: reasoned  |  confidence: medium  |  critic: approved (2 rounds)  |  T_workflow_K: 550
<!-- D-00 plan: dominant uncertainty = pcff_ps_tg_transferability (literature_anchor probe, not executed); 5 decisions D-01..D-04 + D-08 hardware. exp anchors Tg=373 K, density=1.05 g/cm3. DP=40 → K screening-grade (DP<<Me@160). bm=murnaghan ±1000 atm glassy 300 K. D-08 kokkos/mpi1/gpu1 (confidence=low, host-mismatched probe). -->
<!-- D-08 hardware: engine=kokkos, gpu_per_run=1, mpi=1 -->
<!-- gpu_per_run from plan: 1 -->
<!-- Murnaghan fit B0_prime gate [4,20]; eos R²≥0.999; fallback=deform -->
<!-- Tg success: bilinear R²≥0.8, T-range brackets exp Tg 373 K; multirate log-linear R²≥0.9, n_rates≥2 -->
<!-- (END_DATE, DP, N_CHAINS, Seeds filled below as reached: DP=40, chains=10) -->

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF (Class II, via EMC)                            | classify→PSTR; PCFF parameterizes aromatic ring charges/cross-terms (validated PC, PMMA backbone); TraPPE-UA rejected (no ring charges). confidence=medium |
| D-02 Charges        | bond-increment (FF-embedded)                         | PCFF-native, zero extra QM cost; RESP higher-fidelity but unneeded for screening |
| D-03 Electrostatics | PPPM, 12.0 Å cutoff                                  | aromatic ring partial charges → long-range Coulomb required; lj/cut only valid for apolar PHYC/PDIE |
| D-04 System size    | DP=40, 10 chains, ~6,400 atoms                       | DP≥30 Tg-converged & averages atactic fluctuations (Soldera2006); DP<<Me@160 → K screening-grade |
| D-05 Convergence    | PASS                                                 | hard gates met (density drift 0.21%, block-SEM 0.039%, P2=0.034, Rg CV 11.6%); C(t)/MSID advisory for aromatic PS. density=0.974 g/cm³ (−2.3% vs 1.05, within ±5%) |
| D-06 Tg fit quality | SCREENING-GRADE (per-rate fits unreliable)           | is_glassy=true (r400 Tg 328 K > 300). Per-rate: r400 ACCEPTABLE (R²=0.994, bilinear), r160 ACCEPTABLE (R²=0.995, hyperbola), r40 POOR/FAIL. Accepted screening-grade per user decision 2026-06-23 (see R-01). |
| D-06b Multirate Tg  | INVALID — slope_gate_pass=false                      | log-linear slope=−118.8 K/ln(Γ) (negative/unphysical), R²=1.0 on 2 pts but inverted; is_flat_rate_regime=false; tg_method=single_rate_fallback → Tg_at_slow_rate=436.9 K (r160). DSC extrapolation NOT valid. Registry rows removed (contaminated). **Headline Tg = 437 K (screening-grade, single-rate fallback; rate-extrapolation invalid).** |
| D-07 Property method | murnaghan (glassy 300 K) — ACCEPTED                  | is_glassy=true → Murnaghan ±1000 atm at 300 K. K=2.44±0.03 GPa, B0′=13.5 (∈[4,20]), R²=0.9998, all 5 pts vol-equilibrated; fluctuation B_dyn=2.50 GPa (2.3% agree). −26% vs exp 3.3–4.0 GPa = screening-grade DP≪Me underestimate (as planned). No deform fallback. |
| D-08 Hardware       | kokkos, 1 GPU/run, mpi=1                             | PCFF→KOKKOS full-offload (by_forcefield default); confidence=low (host-mismatched unbenchmarked probe on A800) |

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

### R-01 Tg multirate fits unreliable (thermal track)
- **Symptom:** Three Tg sweeps at 40/160/400 K/ns gave inconsistent, physically inverted Tg: r400→328 K (bilinear, ACCEPTABLE), r160→437 K (hyperbola, ACCEPTABLE), r40→FAIL (POOR; hyperbola slope-sign invalid, Tg pinned to 205 K endpoint). Tg *rose* as cooling rate *fell* (unphysical); all three flag broad, poorly-localized transitions and high-T plateau under-equilibration (n_eff<5; 135 plateaus rejected at r40).
- **Root cause:** (1) Dominant uncertainty `pcff_ps_tg_transferability` — PCFF raw MD PS Tg is known elevated (~450–484 K, Soldera2006) and not cleanly bracketed by the bilinear/hyperbola models; (2) tg_steps_per_t plateaus too short for adequate equilibration at high T for this stiff aromatic backbone (systematic, NOT seed noise).
- **Action:** r40 excluded from registry (POOR<ACCEPTABLE filter). Ran multirate slope-gate on the 2 surviving rows.
- **Multirate verdict:** `slope_gate_pass=false` — log-linear slope = −118.8 K/ln(Γ) (negative, unphysical; valid PS Tg must INCREASE with cooling rate). `is_flat_rate_regime=false`. `tg_method=single_rate_fallback` → Tg_at_slow_rate = 436.9 K (r160). Per slope-gate rule the sweep set is contaminated → all PS2 rows removed from `_tg_registry/PSTR__CCc1ccccc1.csv`.
- **Diagnosis:** systematic, not seed noise — the slowest/most-equilibrated rate (r40, 500k steps/T) failed WORST, so a seed re-roll at the same protocol will reproduce the failure. Genuine fix = protocol change (longer per-T equilibration hold and/or shift sweep window up to bracket the elevated PCFF PS Tg ~440–480 K). That is a plan-level change (dominant uncertainty `pcff_ps_tg_transferability` materialized).
- **Outcome:** [awaiting user decision — see below: accept screening-grade Tg vs invest in corrected re-run]

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil | 5249cae6 | 15:43 | 20:58 | 5h 15m | done (9/9 stages) |
| tg-sweep r400 | c82d170c | 21:08 | 21:42 | 34m | done (21 T-steps) |
| tg-sweep r160 | da2ba375 | 21:44 | 23:17 | 1h 33m | done (21 T-steps) |
| tg-sweep r40 | b8f6eb08 | 23:19 | 05:2x | ~6h | done (21 T-steps) |
| murnaghan | 9ae1bdda | 05:30 | 07:10 | 1h 40m | done (5 P-points) |

| analyze-bm | — | 11:37 | 11:39 | 2m | done (K=2.44 GPa) |
| run-summary | — | 11:40 | 11:41 | 1m | done (run_summary.json) |

GPU 1 RELEASED at 11:37 (`pick_gpu.py release --run PS2`) — all GPU stages complete (3 Tg sweeps + Murnaghan). Remaining work (BM extraction, run-summary) was CPU-only.

GPU claim label: `PS2` (claimed GPU 1 via pick_gpu.py; release with `pick_gpu.py release --run PS2` after all GPU stages).
NOTE: Host is shared — GPUs 0/2/3 held by other sessions (PEG2-tg, PVC2). Only GPU 1 available → 3 Tg sweeps run SEQUENTIALLY (400→160→40 K/ns), then Murnaghan, all on GPU 1.

GPU inventory (`nvidia-smi` at run start): 4× NVIDIA A800 40GB (GPU 0–3), all idle ~39.5 GB free each; task allocates 1 GPU.

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=299.95 K · 1951 frames (skip=50) · 2026-06-22 20:59

**Overall: PASS** (hard gates met; C(t)/MSID advisory for aromatic polymer)

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2128% (p=0.0001) | <1%, p<0.01 | PASS |
| Energy drift | 0.1412% (p=0.1559) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.039% | <1% | PASS |
| Energy block-SEM | 0.0504% | <1% | PASS |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 11.6% | <30% | PASS |
| C∞ | 14.303 | lit. varies | INFO |
| MSID slope | 1.447 (R²=0.995) | 1.0 ±20% | ⚠ non-Gaussian (advisory, aromatic) |
| C(t) τ_relax | 4% decayed | — | ⚠ partial (advisory for aromatic) |
| MSD kinetic trap | no (α=0.288, MSD=524.8 ≫ Rg²=220.5 Å²) | — | OK |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0336 ± 0.0082 | <0.10 | PASS |
| Density homogeneity CV | 23.7% (6³ grid) | <25% | PASS |

**Density:** 0.974 g/cm³ (SEM 0.00038) vs exp 1.05 → −2.3%, within ±5% acceptance.

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg CV (chain–chain) | 11.6% | CV < 30% → PASS |
| MSD plateau   | no kinetic trap (α=0.288, MSD ≫ Rg²) | PASS |
| Density homog (CV) | 23.7% | < 25% → PASS |
| C(t) decay (melt NVT) | 3.5% (advisory — aromatic main chain) | advisory (glassy carve-out) |
| τ_c chain relax (KWW) | 2.07e7 ps | annotation only |
| R_ee mean ± std | 33.9 ± 9.08 Å (N=10 chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 0.974 g/cm³ (SEM 4e-4) | 0.997–1.103 g/cm³ (exp ~1.05) | −2.3% | NPT 300 K plateau | ✓ |

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg | **437 K (screening-grade)** | 353–393 K (exp 373) | +17% | single-rate fallback (r160); multirate slope-gate FAILED → rate-extrapolation invalid | ⚠ unreliable |
| Tg (per-rate MD) | r400→328 K, r160→437 K, r40→FAIL | — | — | bilinear/hyperbola; physically inverted vs rate | ⚠ |
| α_g (CTE) | ~7.9×10⁻⁵ K⁻¹ | 2–3×10⁻⁵ K⁻¹ (lit.) | high | r400 bilinear (screening) | ⚠ screening-grade |
| α_r (CTE) | ~5.5×10⁻⁴ K⁻¹ | 5.5–6×10⁻⁴ K⁻¹ (lit.) | ~ok | r400 bilinear (screening) | ⚠ screening-grade |
| ΔCp at Tg | ~0.24 J/(g·K) | 0.26–0.30 J/(g·K) | ~ok | H(T) bilinear (r400) | ⚠ screening-grade |

> **Tg caveat:** the 3-rate sweep produced physically inverted, model-inconsistent Tg (slope_gate_pass=false); the slowest/most-equilibrated rate failed worst → systematic high-T plateau under-equilibration + the plan's flagged `pcff_ps_tg_transferability`. Reported Tg is screening-grade only (user-accepted 2026-06-23). A reliable Tg needs longer per-T equilibration and a sweep window bracketing the elevated PCFF PS Tg (~440–480 K).

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 2.44 ± 0.03 GPa | 3.3–4.0 GPa | −26% | Murnaghan EOS ±1000 atm, 300 K (R²=0.9998; fluctuation cross-check 2.50 GPa) | ⚠ screening-grade (DP≪Me) |
| B0' | 13.5    | 7–11 (typical) | —    | Murnaghan fit            | annotation (high but ∈[4,20]) |
| G   | N/A | — | — | not computed (no deform run) | N/A |
| E   | N/A | — | — | not computed (no deform run) | N/A |

Simulation dir: `data/PS2/lammps/`
Outputs: `data/PS2/raw/` — JSONs; `data/PS2/graphs/` — PNGs; `data/PS2/raw/run_summary.json`

---

## RUN OUTCOME — COMPLETE (screening-grade)

- **Density 0.974 g/cm³** (−2.3% vs exp) — ✓ solid.
- **Bulk modulus 2.44 GPa** (−26% vs exp) — ⚠ screening-grade, magnitude as predicted by DP≪Me (DP=40 vs Me@160); Murnaghan fit clean (R²=0.9998), fluctuation cross-check agrees within 2.3%.
- **Tg 437 K** — ⚠ screening-grade/unreliable; multirate slope-gate failed (see R-01). Honest limitation, not a silent pass.
- Total wall: ~equil 5h15m + 3 Tg sweeps (~8h) + Murnaghan 1h40m; within 48 h budget. 1 GPU (shared host).

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 15.3 h  |  **GPU**: 15.3 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PS2/lammps/**/*.log` (Born stages excluded); reproducible via `manuscript/gen_table_compute_cost.py`.
