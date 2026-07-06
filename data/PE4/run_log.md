# Polyethylene (PE) Run PE4 · 2026-06-25 → 2026-06-26
SMILES: `*CC*`  |  FF: TraPPE-UA  |  Charges: none  |  DP: [DP]  |  Chains: [N_CHAINS]  |  GPU: [IDs used]
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=942725  |  SEED_HOT=618758 (600K softheat)  |  SEED_COLD=846205 (300K)
Plan: `data/PE4/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved (1 round, 0 findings)  |  T_workflow_K: 300

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | TraPPE-UA                | classify_polymer → PHYC → EMC TraPPE-UA auto-routed (Ramos 2015) |
| D-02 Charges        | none (embedded in FF)        | TraPPE-UA united-atom, nonpolar PE backbone |
| D-03 Electrostatics | lj/cut 14 Å                          | pure C/H hydrocarbon → no long-range Coulomb |
| D-04 System size    | DP=120, 20 chains                        | polymer_rules.json PHYC default |
| D-05 Convergence    | PASS (rubbery carve-out)                         | overall_pass=False→PASS: density SEM 0.035%, CV 12.9%, energy drift 0.58% all pass; C(t)/MSD advisory (rubbery) |
| D-06 Tg fit quality | EXCELLENT (all 3 rates)  | r10 R²=0.9962, r25 R²=0.9951, r40 R²=0.9978; is_glassy=FALSE (Tg@r40=235 K < 300 K → rubbery) |
| D-06b Multirate Tg  | rubbery-flat-mean = 225.3 K  | rates [10,25,40] K/ns → Tg [213,228,235]; log-linear b=15.94 K/ln, R²=0.9995, span 0.60 dec; rubbery_regime_exemption=True, slope_gate_pass=True; VF underconstrained (POOR, <2 dec) — diagnostic only. NOTE: rubbery-regime estimate, NOT DSC extrapolation |
| D-07 Property method | murnaghan (rubbery)  | is_glassy=False; rubbery Murnaghan EOS @300 K, bm_pressures=[1,500,1000,2000,5000] atm; fluctuation K cross-check |

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

No simulation failures or recoveries — all stages (build → equil → 3 Tg sweeps → Murnaghan) completed first-pass on GPU 0.

**Final grade: 2 PASS / 1 FAIL.**
- ✓ Density 0.862 g/cm³ (vs amorphous TraPPE-UA PE 0.855, +0.8%)
- ✓ Bulk modulus 1.558 GPa (within exp 1.5–2.0 GPa; B0'=9.61, R²=0.9999)
- ⚠ Tg 225.3 K (rubbery-flat-mean) vs exp 187 K (+20%): all three per-rate bilinear fits were EXCELLENT (R²≥0.995), but the 10–40 K/ns MD cooling rates are ~70,000× faster than DSC, and the 0.6-decade rate span (<2 decades) cannot support a Vogel–Fulcher extrapolation to the experimental rate. The reported value is a rubbery-regime estimate, not a DSC-equivalent. This is the known TraPPE-UA fast-cool Tg overprediction for PE — a force-field + cooling-rate limitation, not a fit or convergence failure.

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil | efeec2a8 | 23:08 | 00:30 | ~1.4h | done (9/9) |
| tg-sweep r10 | 1d134bae | 00:33 | 04:14 | ~3.7h | done (18 T) |
| tg-sweep r25 | 6d5328ab | 04:18 | 05:44 | ~1.4h | done (18 T) |
| tg-sweep r40 | 4520afc0 | 05:46 | 06:41 | ~55m | done (18 T) |
| murnaghan (rubbery) | c53b0e23 | 06:52 | 07:14 | ~22m | done (5 P) |

GPU claim label: `PE4` → GPU [0] — RELEASED 07:14 after all sims done. GPU 1/2/3 busy (other sessions) — tracks ran sequentially on GPU 0.
Thermal seeds: r10 velocity_seed=51570, r25=969348, r40=352865.
Staged Tg registry (commit after multirate gate; rubbery exemption → commit):
  r10=213.0 K (EXCELLENT, R²=0.9962, α_g=1.88e-4, α_r=7.02e-4, ΔCp=0.4514).
  r25=228.0 K (EXCELLENT, R²=0.9951, α_g=2.19e-4, α_r=6.81e-4, ΔCp=0.4423). velocity_seed=969348.
  r40=235.0 K (EXCELLENT, R²=0.9978, α_g=1.86e-4, α_r=7.34e-4, ΔCp=0.454). velocity_seed=352865.
is_glassy = (Tg@r40=235 > 300) = FALSE → RUBBERY. Mechanical = rubbery Murnaghan (is_glassy false).

GPU inventory (`nvidia-smi` at run start): GPU 0: 40 GB, ~40 GB free (0% util); GPU 1: 40 GB, ~40 GB free (0% util); GPU 2/3: busy (other workloads). Plan: claim GPU 0 (and 1 if needed).

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=299.72 K · 951 frames analysed (skip=50) · 2026-06-26 00:10

**Overall: FAIL → PASS (rubbery regime carve-out)**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1224% (p=0.0041) | <1%, p<0.01 | PASS |
| Energy drift | 0.5788% (p=0.0032) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0347% | <2% (rubbery gate) | PASS |
| Energy block-SEM | 0.1189% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 19.2% | <30% | PASS |
| MSID slope | 1.12 (R²=0.9946) | 1.0 ±20% | OK |
| C(t) τ_relax | 4172607 ps (3% decayed) | — | ⚠ advisory (rubbery) |
| MSD kinetic trap | yes (α=0.203, MSD=579.45 Å² << Rg²=684.6) | — | ⚠ advisory (rubbery <300K) |
| R_ee mean ± std | 58.36 ± 21.05 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0238 ± 0.0057 | <0.10 | PASS |
| Density homogeneity CV | 12.9% (6³ grid, 22.4 atoms/voxel) | <25% (rubbery gate) | PASS |

**Verdict:** PASS under rubbery regime exemption (density block-SEM<2%, density CV<25%, energy drift<1% all satisfied; C(t) decay & MSD kinetic trap advisory only).

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | CV 19.2% | CV < 30% → PASS |
| MSD plateau   | still diffusing (subdiffusive, rubbery) | advisory (rubbery) |
| Density homog (CV) | 12.9% | < 25% → PASS |
| C(t) decay (melt NVT) | 2.7% at end (τ_relax >> trajectory) | advisory (rubbery) |
| τ_c chain relax (KWW) | 4172607 ps | annotation only |
| R_ee mean ± std | 58.36 ± 21.05 Å (N=20 chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 0.862 ± 0.004 g/cm³ | 0.855 (amorphous TraPPE-UA) | +0.8% | NPT 300K plateau | ✓ |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (rubbery-flat-mean) | 225.3 K | 187 (exp); grading band 175–215 | +20% (vs 187); +4.8% over band | mean of multirate Tg (rubbery; not DSC extrap) | ⚠ FAIL |
| Tg (MD @40 K/ns) | 235.0 K   | —                      | —    | bilinear fit, highest screening rate | annotation |
| α_g (CTE) | 18.6–21.9×10⁻⁵ K⁻¹   | ~2–3×10⁻⁴ (amorphous PE) | —   | −a_glassy / ρ_mean_glassy (r10–r40 range) | ✓ |
| α_r (CTE) | 68.1–73.4×10⁻⁵ K⁻¹   | ~6–8×10⁻⁴ (amorphous PE) | —   | −a_rubbery / ρ_mean_rubbery (r10–r40 range) | ✓ |
| ΔCp at Tg | 0.44–0.45 J/(g·K)     | ~0.6 (PE lit.)        | ~25% | H(T) bilinear fit         | ⚠ |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 1.558 ± 0.09 GPa | 1.5–2.0 GPa    | within range | Murnaghan EOS (rubbery, 5-pt [1,500,1000,2000,5000] atm @300 K, R²=0.9999) | ✓ |
| B0' | 9.61    | 7–11 (typical) | —    | Murnaghan fit (rubbery); fit_converged=True | annotation |
| G   | N/A | —    | —    | deformation (glassy only) — N/A rubbery | N/A |
| E   | N/A | —    | —    | deformation (glassy only) — N/A rubbery | N/A |

Fluctuation cross-check B_dyn=1.666±0.103 GPa (divergence 6.9% < 15%, consistent). No vitrification kink (max consecutive dV/dP ratio 1.74× < 3×).

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 8.1 h  |  **GPU**: 8.1 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PE4/lammps/**/*.log` (Born stages excluded); reproducible via `paper/gen_table_compute_cost.py`.
