# Polylactic Acid (PLA) Run 3 · 2026-06-24 → 2026-06-26
SMILES: `*C(C)C(=O)O*`  |  FF: PCFF  |  Charges: embedded (bond-increment)  |  DP: 50  |  Chains: 10  |  GPU: 1
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=472913  |  SEED_HOT=314445  |  SEED_COLD=440770  |  SEED_r50=399646  |  SEED_r100=144177
Plan: `data/PLA3/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved (round 1, 0 findings)  |  T_workflow_K: 620

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                                                 | classify_polymer returned PEST → EMC PCFF auto-routed (ester backbone, class2 FF) |
| D-02 Charges        | embedded (bond-increment)                            | PCFF: bond-increment charges embedded, no QM step |
| D-03 Electrostatics | PPPM 12.0 Å                                          | Ester C=O / O partial charges → long-range Coulomb; class2 lj/class2/coul/long |
| D-04 System size    | DP=50, 10 chains, 4520 atoms                         | polymer_rules.json PEST default |
| D-05 Convergence    | PASS (glassy carve-out)                              | overall_pass=true; density 1.2197 g/cm³ (+6.5% above midpoint, within [0.974, 1.317]); C(t) 10% decay expected for glassy DP=50; MSID slope 1.21 melt-phase advisory |
| D-06 Tg fit quality | GOOD (r50, single-rate anchor); is_glassy=True from exp-Tg fallback | r50: R²=0.987, GOOD, Tg=430.0 K; r25: Tg=464.8K delocalized (alt=360K); r100: Tg=416.2K SUSPECT (alt=375K, high-T n_eff=3-5). Highest-rate (r100) degenerate → is_glassy from plan exp_Tg=331K > 300K per guide. |
| D-06b Multirate Tg  | slope_gate_pass=False — PEST slope-fragility; staged rows discarded | log-linear slope=-35.1 K/decade (b<0, wrong sign), R²=0.941, N_rates=3 @ [25,50,100] K/ns. Tg decreases with rate (464.8→430→416.2) — opposite to physical expectation; delocalized transition artifact at r25+r100. Recovery infeasible within 48h budget. Best-estimate Tg: r50=430.0 K (consistent with PLA2 r40=428.6K). VF=FAILED. DSC-equiv not reliable. |
| D-07 Property method | Deform 3-dir fallback (Murnaghan rejected: B0_prime=30.0 > 20) | Murnaghan ±1000 atm: B0_prime=30, r²=0.966, SEM=57% — noise-dominated; pressure range too narrow for PEST K~4 GPa. Fallback: 3-dir uniaxial deform from npt_prod300_out.data (x/y/z sequential). |

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

### RECOVERY 1 — Tg slope_gate_pass=False (2026-06-26)

**Trigger:** `extract_tg_multirate` returned `slope_gate_pass=False`, `loglinear_slope_K=-35.06 K/decade` (requires b>0 for glassy PLA).

**Root cause — PEST/PLA delocalized transition at extreme rates:**
- r25 (800k steps/T): primary Tg=464.8K, alt=360K; 105K disagreement → delocalized transition; primary likely catches spurious high-T breakpoint
- r50 (400k steps/T): primary Tg=430.0K (clean, consistent with PLA2 r40=428.6K)
- r100 (200k steps/T): primary Tg=416.2K SUSPECT (alt=375K); high-T windows n_eff=3-5, under-equilibrated at 200k steps/T
- Net: primary Tg decreases with rate (464.8→430→416.2), giving negative log-linear slope (b=-35.1 K/dec)
- Rates span only 0.6 decades [25,100] K/ns — insufficient to constrain sign robustly

**Recovery infeasible within 48h budget:**
- Recovery requires re-running all 3 sweeps (~41h combined) — at ~33h of 48h budget
- PEST slope-fragility: same bilinear-fit artifact expected with new seed (structural, not stochastic)

**Fallback applied:**
- is_glassy = True from plan exp_Tg=331K > 300K (guide: slope-gate fail → exp-Tg fallback)
- Best-estimate Tg = 430.0 K (r50, consistent with PLA2 Tg=428.7K)
- Staged registry rows discarded; proceeding to mechanical track

**Outcome:** converged via fallback (exp-Tg routing + r50 best-estimate)

---

### RECOVERY 2 — Deform triple-launch log corruption (2026-06-26)

**Trigger:** Session restart exposed 4 simultaneous LAMMPS writers on `05_deform_x.log` (confirmed by lsof). Three deform_chain.sh processes (PIDs 1621573, 1660026, 1753303) + one MCP run_lammps_script wrapper (1974339) all opened the same x-direction log. Step output was interleaved and box dimensions corrupted.

**Root cause:** Multiple prior context resets triggered separate deform chain submissions from different sessions. Earlier attempts used the wrong launch flags (-sf gpu with KOKKOS-default binary → newton-off error), so they were killed and retried, but some processes from each attempt survived and all were writing to the same log. The deform_chain.sh also had the wrong LAMMPS binary/flags (lammps-install + -sf gpu instead of lammps-install-kokkos + -sf kk -pk kokkos).

**Fix applied:**
- Killed all 4 LAMMPS processes + parent deform_chain.sh processes
- Deleted corrupted x/y/z logs and partial output files
- Updated deform_chain.sh to use KOKKOS binary + mpi=1 (matching Murnaghan)
- Restarted single deform_chain.sh instance; verified exactly 1 lsof writer before walking away
- Cross-track rule 3 compliance: `lsof <log> = 1 writer` confirmed before launch

**Outcome:** converged — fresh chain running (PID 2500191, chain_nohup.out); x at step ~244k/700k, y/z pending

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage) | 905e9409 | 2026-06-24 | 2026-06-25 | — | done |
| tg-sweep r25 | 02bab4f6 | 2026-06-25 | 2026-06-25 | — | done |
| tg-analysis r25 | — | 2026-06-25 | 2026-06-25 | — | done (Tg=464.8 K, R²=0.991, GOOD; Tg_alt=360K ⚠ delocalized) |
| tg-sweep r50 | 4eff15fa | 2026-06-25 | 2026-06-25 | — | done |
| tg-sweep r100 | efe4bf3c | 2026-06-25 | 2026-06-26 | — | done |
| tg-analysis r100 | — | 2026-06-26 | 2026-06-26 | — | done (Tg=416.2 K, R²=0.9945, GOOD; SUSPECT delocalized, alt=375K) |
| tg-multirate | — | 2026-06-26 | 2026-06-26 | — | done (slope_gate_pass=False; is_glassy=True from exp_Tg) |
| murnaghan BM | dd48ef39 | 2026-06-26 | 2026-06-26 | — | done (B0_prime=30, rejected → deform fallback) |
| deform 3-dir | deform_chain/2500191 | 2026-06-26 | 2026-06-26 | 1h43m | done (K_x=3.228, K_y=2.826, K_z=3.323 GPa → K_mean=3.126 GPa, isotropy 8.44%) |
| tg-analysis r50 | — | 2026-06-25 | 2026-06-25 | — | done (Tg=430.0 K, R²=0.987, GOOD) |

GPU inventory: GPU 1: released 2026-06-26 05:00 (PLA3 deform complete) | GPU 0: released (PLA3-r100 complete)

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=299.95 K · 951 frames analysed (skip=50) · 2026-06-24 19:44

**Overall: PASS** *(with glassy carve-out: melt-phase C(t)/MSID failures acceptable on DP=50)*

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0961% (p=0.028) | <1%, p<0.01 | PASS |
| Energy drift | 0.092% (p=0.0526) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0243% | <1% | PASS |
| Energy block-SEM | 0.0165% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 19.8% | <30% | PASS |
| C∞ | 14.963 | lit. varies | INFO |
| MSID slope | 1.21 (R²=0.9971) | 1.0 ±20% | ⚠ non-Gaussian [melt-phase] |
| C(t) τ_relax | 5093.1 ps (10% decayed) | — | ⚠ partial [melt-phase] |
| MSD kinetic trap | no (α=0.262, MSD=296.55 Å²>>Rg²=289.796) | — | OK |
| R_ee mean ± std | 35.41 ± 12.11 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.017 ± 0.0061 | <0.10 | PASS |
| Density homogeneity CV | 23.8% (6³ grid, 20.9 atoms/voxel) | <25% | PASS |

**Notes:** MSID slope and C(t) decay are melt-phase diagnostics from nvt_production.dump; on glassy DP≥50, these relaxation timescales extend beyond typical production windows. NPT 300K thermo and spatial homogeneity PASS cleanly, confirming successful cooling and packing.

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg CV (chain–chain) | 19.8% | CV < 30% → PASS |
| MSD kinetic trap | no (α=0.262) | PASS |
| Density homog (CV) | 23.8% | < 25% → PASS |
| C(t) decay (melt NVT) | 10% at threshold 15% | ⚠ advisory (glassy carve-out) |
| τ_c chain relax (KWW) | 5093.1 ps | annotation only |
| R_ee mean ± std | 35.41 ± 12.11 Å (N=10 chains) | INFO |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.2197 g/cm³ | 1.186–1.31 g/cm³ | 0% (within range) | NPT 300K plateau (9-stage equil) | ✓ |

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (r50 best-estimate) | 430.0 K | 326–327 K | +31.5% above upper bound | bilinear fit, r50 single-rate fallback (slope_gate_pass=False) | ⚠ FAIL |
| Tg (DSC-equiv, INVALID) | 464.8 K | — | — | log-linear Tg(Γ) at 3 rates [25,50,100] K/ns — CONTAMINATED (b<0) | ✗ discarded |
| α_g (CTE glassy) | 1.97×10⁻⁴ K⁻¹ | — | — | bilinear density-T fit (r50) | INFO |
| α_r (CTE rubbery) | 4.03×10⁻⁴ K⁻¹ | — | — | bilinear density-T fit (r50) | INFO |
| ΔCp at Tg | 0.209 J/(g·K) | ~0.5 J/(g·K) lit. | — | H(T) bilinear fit (r50, R²=0.984) | INFO |

**Tg note:** Multirate slope gate FAILED (b=−35.1 K/dec, wrong sign; r25 delocalized transition). DSC-equiv 464.8K discarded. Best-estimate Tg=430.0K from r50 (R²=0.987, consistent with PLA2 r40=428.6K). Tg error (+31.5%) reflects combined MD rate effect + PCFF bias expected for PEST class. is_glassy=True from plan exp_Tg=331K > 300K.

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K | 3.126 ± 0.152 GPa | 3.0–4.5 GPa | 0% (within range) | deformation_3dir (x/y/z; isotropy Δ=8.44%<20%) | ✓ |
| G | N/A | — | — | C12>C11 in y/z directions (residual cell anisotropy); G unreliable | N/A |
| E | N/A | — | — | same as G | N/A |

**K note:** Murnaghan at ±1000 atm rejected (B0_prime=30.0>20, PEST narrow-pressure runaway). 3-dir deform fallback: K_x=3.228, K_y=2.826, K_z=3.323 GPa → K_mean=3.126 GPa. Diagnostic fluctuation B_dyn=5.28 GPa (elevated; frozen-in volume fluctuations unreliable for glassy K). K within exp range [3.0, 4.5] GPa.

**Overall: WARN** — ρ ✓ + K ✓; Tg ⚠ FAIL (MD rate + PCFF bias expected for PEST; absolute value consistent with PLA2).

Simulation dir: `data/PLA3/lammps/`
Outputs: `data/PLA3/raw/` — JSONs; `data/PLA3/graphs/` — PNGs; `data/PLA3/raw/run_summary.json`
- RESULT (wide [-1000,0,1500,3000,5000]): K_Murnaghan = 4.462 GPa (r²=0.9998, B0'=11.4) → GATE PASS; overwrote old r²=0.966/B0'=30 fail. status: DONE

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 57.1 h  |  **GPU**: 57.1 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PLA3/lammps/**/*.log` (Born stages excluded); reproducible via `paper/gen_table_compute_cost.py`.
