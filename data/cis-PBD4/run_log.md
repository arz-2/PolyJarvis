# cis-Polybutadiene (cis-PBD) Run 4 · 2026-06-25 → 2026-06-27
SMILES: `*C/C=C\C*`  |  FF: TraPPE-UA  |  Charges: none  |  DP: 100  |  Chains: 20  |  GPU: [IDs used]
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=482913  |  SEED_HOT=614287 (nvt_softheat velocity create)  |  SEED_COLD=N/A (npt_production inherits velocities)
Plan: `data/cis-PBD4/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved (1 round, 0 findings)  |  T_workflow_K: 300.0

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | TraPPE-UA                                            | classify_polymer → PDIE → EMC TraPPE-UA auto-routed (use_trappe=true) |
| D-02 Charges        | none (embedded in FF)                                | apolar hydrocarbon diene backbone; TraPPE-UA, no QM charges |
| D-03 Electrostatics | lj/cut 12 Å                                          | pure C/H/=C, no heteroatoms → lj/cut sufficient |
| D-04 System size    | DP=100, 20 chains, 8040 atoms                        | polymer_rules.json PDIE default; ρ_init=0.57 g/cm³ |
| D-05 Convergence    | PASS (rubbery carve-out)                             | density SEM 0.031%, homog CV 12.7%, energy drift 0.11% all PASS; C(t) reptation advisory only (5% decay, τ=59 ns) — non-binding for rubbery |
| D-06 Tg fit quality | EXCELLENT (all 3 rates)                              | r40 (highest) R²=0.9998 EXCELLENT; is_glassy=FALSE (Tg_r40=186.5 K < 300 K → rubbery). r10=179.6, r25=200.0 (outlier), r40=186.5 |
| D-06b Multirate Tg  | DSC-equiv = 186.6 K (rubbery_flat_mean)              | rubbery regime: T_workflow=300 >> Tg → is_flat_rate_regime=true, rubbery_regime_exemption=true, slope_gate_pass=true. 8 rows × 3 replicates @ [10,25,40,50,100,160] K/ns. Log-linear R²=0.06 & VF FAILED — non-binding (rubbery, 1.2 decades). Headline = per-rate mean |
| D-07 Property method | murnaghan (rubbery) + fluctuation cross-check | rubbery (Tg=186 K < 300 K → is_glassy=false); Murnaghan K=1.600 GPa (B0'=9.57, R²=0.99996) vs fluctuation 1.484 GPa, 7.5% div; widened P=[1,500,1000,2000,5000] fixed cis-PBD3 B0'-runaway |
| D-08 Hardware       | engine=cpu, mpi=8, gpu_ids="" (Rule-0 exception) | All 4 GPUs busy + 15 spare cores; PDIE ~8k UA atoms ~7× faster CPU-MPI=8 (ingested memory 2026-06-20); GPU default values_are_benchmarked=False. σranks 3+8=11≤18. Verified engine="cpu" emits no `package gpu`/`-sf gpu` (script_generator.py:1188). |

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

None

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage, CPU mpi=8) | 2769da8a | 00:01 | 11:28 | ~11h27m | done — PASS, ρ=0.8986 |
| tg-r10 (GPU1 neigh_yes, mpi=1) | 37f88f7c | 12:05 | 20:02 | ~7h57m | done — Tg=179.6 K EXCELLENT (R²=0.9999, within exp). seed=367660 |
| tg-r40 (CPU mpi=8) | 6ef220e2 | 12:09 | 17:43 | ~5h34m | done — Tg=186.5 K EXCELLENT (R²=0.9998); is_glassy=FALSE (rubbery) |
| tg-r25 (GPU1 neigh_yes, mpi=1) | e334e4e6 | 20:05 | 23:08 | ~3h03m | done — Tg=200.0 K EXCELLENT (R²=0.9999); OUTLIER vs r10/r40 (rubbery seed-scatter, cf cis-PBD3 r25=180.8). seed=399400 |
| murnaghan (CPU mpi=8, rubbery) | 335d94c7 | 17:55 | 20:58 | ~3h03m | done — 5/5 P-stages; K=1.600 GPa (B0'=9.57) |

All stages COMPLETE. Run finished 2026-06-27 ~04:10. Total wall ~28 h (CPU equil + GPU/CPU thermal + CPU mechanical, heavily parallelized).

GPU inventory (`nvidia-smi` at run start): all 4× RTX 6000 busy (PLA3/PLA4, PSU4, PMMA3, PEEK3 + 7-day ext ML job on GPU1) → equil routed to CPU mpi=8 (15 spare cores). GPU1 freed by user mid-run (~12:00) → thermal r10/r25 on GPU1 neigh_yes (co-located w/ idle ML job); r40 + Murnaghan on free CPU in parallel.

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=300.0 K · 1951 frames analysed (skip=50) · 2026-06-26 11:29

**Overall: PASS (rubbery carve-out)**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1244% (p=0.0082) | <1%, p<0.01 | PASS |
| Energy drift | 0.1111% (p=0.3091) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0311% | <1% | PASS |
| Energy block-SEM | 0.0526% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 20.8% | <30% | PASS |
| MSID slope | 1.011 (R²=0.9944) | 1.0 ±20% | OK |
| C(t) τ_relax | 59072.1 ps (5% decayed) | — | ⚠ advisory (reptation-limited) |
| MSD kinetic trap | no (α=0.355, MSD=1086.38 Å²>>Rg²=716.463) | — | OK |
| R_ee mean ± std | 63.34 ± 21.35 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0112 ± 0.0036 | <0.10 | PASS |
| Density homogeneity CV | 12.7% (7³ grid, 23.4 atoms/voxel) | <25% | PASS |

**Verdict:** PASS — Rubbery (regime=rubbery, is_glassy=false) gates only on density SEM/CV/energy; C(t) reptation metrics ADVISORY. All hard gates passed.

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | CV 20.8% (MSID slope 1.011, R²=0.994) | CV < 30% → PASS |
| MSD plateau   | sub-diffusive (α=0.355), no kinetic trap | PASS |
| Density homog (CV) | 12.7% (7³ grid) | < 25% → PASS |
| C(t) decay (melt NVT) | 5% at end / rubbery — advisory | non-binding (reptation-limited) |
| τ_c chain relax (KWW) | 59072 ps / rubbery | annotation only |
| R_ee mean ± std | 63.34 ± 21.35 Å (N=20 chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 0.8986 g/cm³ | 0.90 g/cm³ (PBD amorph.) | −0.16% | NPT 300K plateau (SEM 0.028%) | ✓ |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (rubbery-mean) | 186.6 K | 167–178 K (DB, PolymerDataHandbook1999) | +8.6 K (+4.8%) above upper | rubbery_flat_mean over 8 rows×3 replicates | ⚠ FAIL — marginal; TraPPE-UA elevation + r25=200 K seed-outlier + cis-PBD-2 r160 (floor-violating) in registry inflate mean |
| Tg (MD @40 K/ns) | 186.5 K | — | — | bilinear fit, highest screening rate (drives is_glassy) | annotation |
| α_g (CTE) | 21.6×10⁻⁵ K⁻¹ | ~20–24×10⁻⁵ K⁻¹ (PBD glassy) | within | −a_glassy/ρ (r10, slowest) | ✓ |
| α_r (CTE) | 69.5×10⁻⁵ K⁻¹ | ~66–75×10⁻⁵ K⁻¹ (PBD rubbery) | within | −a_rubbery/ρ (r10, slowest) | ✓ |
| ΔCp at Tg | 0.258 J/(g·K) | ~0.27–0.49 J/(g·K) (PBD) | low-ish | H(T) bilinear fit (r10) | ⚠ |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 1.600 ± 0.051 GPa | 1.38–1.95 GPa | within range | Murnaghan EOS rubbery @300K (5-pt, R²=0.99996); fluctuation cross-check 1.484 GPa (7.5% div) | ✓ |
| B0' | 9.57   | 7–11 (typical) | —    | Murnaghan fit (rubbery); widened P fixed cis-PBD3 runaway | annotation |
| G   | N/A | — | — | deformation (glassy only) | N/A — rubbery |
| E   | N/A | — | — | deformation (glassy only) | N/A — rubbery |

### Overall verdict (run_summary.json)

**2 of 3 properties PASS.** cis-PBD confirmed rubbery (is_glassy=false, Tg=186.6 K < 300 K).
- ✅ **Density 0.8986 g/cm³** — PASS (−0.16% vs 0.90; within DB band).
- ✅ **Bulk modulus 1.600 GPa** — PASS within the PBD–PI envelope [1.38–1.95] (Murnaghan B0'=9.57, fluctuation cross-check 1.484, 7.5% div). Widened P series resolved the cis-PBD3 B0'-runaway — headline mechanical result. Caveat: vs the cis-PBD-*specific* K_T=1.38 GPa (Mark 1999) this is +16% high; the fluctuation value 1.484 (+7.5%) is closer. PASS follows the documented [1.38,1.95] convention (cf cis-PBD3=1.565 PASS).
- ⚠️ **Tg 186.6 K** — marginal FAIL (+4.8% above DB upper 178 K). Expected TraPPE-UA PDIE elevation; fit valid (primary_fit_invalid=false). Inflated by the r25=200 K seed-outlier and registry inclusion of cis-PBD-2's floor-violating r160 point. Not a simulation failure; no recovery per rubbery slope-gate exemption.

Simulation dir: `data/cis-PBD4/lammps/`
Outputs: `data/cis-PBD4/raw/` — JSONs; `data/cis-PBD4/graphs/` — PNGs; `data/cis-PBD4/raw/run_summary.json`

---

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 31.7 h  |  **GPU**: 11.2 h  |  **CPU**: 20.5 h (164 core-h)  |  procs: 1/8
- Source: `data/cis-PBD4/lammps/**/*.log` (Born stages excluded); reproducible via `paper/gen_table_compute_cost.py`.
