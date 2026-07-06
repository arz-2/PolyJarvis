# PEEK (Poly ether ether ketone) Run 3 · 2026-06-24 → [END_DATE]
SMILES: `*Oc1ccc(Oc2ccc(C(=O)c3ccc(cc3)*)cc2)cc1`  |  FF: PCFF  |  Charges: bond-increment  |  DP: 32  |  Chains: 8  |  GPU: 2
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=481572  |  SEED_HOT=936090  |  SEED_COLD=N/A
Plan: `data/PEEK3/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved round 1  |  T_workflow_K: 770.0

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF (EMC builder)                                   | classify_polymer returned PKTN → EMC PCFF auto-routed; PCFF covers aromatic ketone carbonyl + aryl ether torsions via Class II cross terms |
| D-02 Charges        | bond-increment (embedded in PCFF)                    | EMC: charges embedded, no QM step; PCFF bond-increments for C=O and aryl ether |
| D-03 Electrostatics | PPPM 12 Å                                            | ketone C=O and aryl ether partial charges → long-range Coulomb required |
| D-04 System size    | DP=32, 8 chains, ~9,344 atoms est.                   | polymer_rules.json default; dp=32 nchain=8 (MW~7,381 g/mol; above Klajmon2023 ~9k threshold borderline — screening budget) |
| D-05 Convergence    | PASS                                                  | overall_pass=True; density 1.199 g/cm³ (−0.1% vs lower bound 1.2); thermo clean; C(t) 19% partial decay expected for rigid aromatic PKTN |
| D-06 Tg fit quality | GOOD (single-rate r25 only)                          | R²=0.990, N=58 bins, GOOD; Tg_MD=551.7 K @ 25 K/ns (alt=523.5 K); is_glassy=True (551.7 K >> 300 K); CTE α_g=1.93×10⁻⁴, α_r=4.27×10⁻⁴ K⁻¹ (ratio 2.21 ✓); ΔCp=0.105 J/(g·K); primary_fit_invalid=False |
| D-06b Multirate Tg  | N/A — single-rate only                               | User decision: skip r50, r100; single-rate Tg_MD=551.7 K @ 25 K/ns reported. No DSC-equivalent extrapolation. Slope gate N/A. |
| D-07 Property method | murnaghan (glassy, 300 K)                            | Tg_MD=551.7 K → is_glassy=True; ±1000 atm, 5 points; K=5.306±0.058 GPa, B0'=7.60, R²=0.9998; PASS vs exp [4.0, 5.8] GPa |

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

### R-01 — npt_pppm I/O error (disk full)
- **Stage:** npt_pppm (stage 4 of 9), step 20,000 of 500,000
- **Symptom:** `ERROR: I/O error while writing restart (src/write_restart.cpp:375)` — LAMMPS could not write restart file; Claude Code /tmp also at 0 MB
- **Root cause:** Home filesystem filled to capacity; restart write failed mid-run
- **Fix:** User freed 46 GB disk space; partial npt_pppm outputs deleted; re-submitted stages 4–9 from npt_compress_out.data
- **Outcome:** Recovery chain submitted — converged

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage) | 16c67484 | 08:39 | — | — | failed (npt_pppm, disk full) |
| equil-recovery (6-stage) | 5bb5ad9c | recovery | 21:49 | 21:49 | done |
| tg-sweep r25 K/ns | 168d6309 | Phase B | done | 36:50 | done (750→250K complete) |

GPU inventory: GPU 3 (RTX 6000 24 GB), claimed as PEEK3-bm. MPI=1, engine=kokkos.
GPU claim label: PEEK3-bm

| murnaghan BM | 8e75d754 | Phase B mech | done | ~3.5h | done (5/5 points) |

---

## D-05 CONVERGENCE DETAIL

## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.98 K · 1951 frames analysed (skip=50) · 2026-06-24 21:52

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0142% (p=0.6319) | <1%, p<0.01 | PASS |
| Energy drift | 0.0055% (p=0.8861) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0231% | <1% | PASS |
| Energy block-SEM | 0.012% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 28.1% | <30% | PASS |
| MSID slope | 0.942 (R²=0.992) | 1.0 ±20% | OK |
| C(t) τ_relax | 25921.7 ps (19% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.221) | — | ⚠ trapped |
| R_ee mean ± std | 67.32 ± 42.71 Å (N=8 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.024 ± 0.0075 | <0.10 | PASS |
| Density homogeneity CV | 20.5% (7³ grid, 25.4 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed (19%, τ_relax=25922 ps >> trajectory 1.95 ns); MSD kinetic trap — both expected for rigid aromatic PKTN/PEEK at 300 K (require_glassy carve-out applied)

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | [X ± Y] Å | CV < 30% → [PASS / FAIL] |
| MSD plateau   | [plateau / still diffusing] | [PASS / FAIL] |
| Density homog (CV) | [X]% | < 25% → [PASS / FAIL] |
| C(t) decay (melt NVT) | [X%] at threshold [Y] / N/A — rubbery | [PASS / FAIL] |
| τ_c chain relax (KWW) | [X] ps / N/A — rubbery | annotation only |
| R_ee mean ± std | [X ± Y] Å (N=[N] chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.199 g/cm³ | 1.263 g/cm³ (amorphous) | −5.1% | NPT 300 K plateau | ⚠ FAIL* |

*Boundary FAIL: run_summary lower bound 1.200, simulated 1.199 (−0.1% margin). PCFF systematic ~−5% underestimate for amorphous PEEK — qualitatively expected.

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (MD @ 25 K/ns) | 551.7 K | 405–431 K | +28% MD rate effect | bilinear fit, r25 single-rate | ⚠ FAIL† |
| Tg (DSC-equiv) | N/A | — | — | single-rate only (no multirate) | N/A |
| α_g (CTE) | 1.93×10⁻⁴ K⁻¹ | — | — | bilinear slope glassy region | — |
| α_r (CTE) | 4.27×10⁻⁴ K⁻¹ | — | — | bilinear slope rubbery region | — |
| ΔCp at Tg | 0.105 J/(g·K) | — | — | H(T) bilinear fit | — |

†MD Tg at r25 (25 K/ns) inherently ~130 K above DSC Tg due to rate effects. Single-rate decision by user (no r50/r100); no DSC-equivalent extrapolation available.

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K | 5.306 ± 0.058 GPa | 4.0–5.8 GPa | 0.0% (within range) | Murnaghan NPT ±1000 atm @ 300 K, B0'=7.60, R²=0.9998 | ✓ PASS |
| B0' | 7.60 | 7–11 (typical) | — | Murnaghan fit | annotation |

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 52.1 h  |  **GPU**: 52.1 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PEEK3/lammps/**/*.log` (Born stages excluded); reproducible via `paper/gen_table_compute_cost.py`.
