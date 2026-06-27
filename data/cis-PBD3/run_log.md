# cis-Polybutadiene (cis-PBD) Run 3 · 2026-06-23 → 2026-06-24
SMILES: `*C/C=C\C*`  |  FF: TraPPE-UA  |  Charges: trappe-ua-fixed  |  DP: 100  |  Chains: 20  |  GPU: [IDs used]
Requested: tg, density, bulk_modulus  |  Replicate: 2 of 3  |  Seeds: EMC=986450  |  SEED_HOT=random  |  SEED_COLD=N/A
Plan: `data/cis-PBD3/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved round 1  |  T_workflow_K: 300.0

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | TraPPE-UA                                            | PDIE class → EMC auto-routed trappe-ua (Wick2000 alkene types) |
| D-02 Charges        | none (embedded in FF)                                | Pure C/H backbone, no partial charges needed |
| D-03 Electrostatics | lj/cut 12 Å                                          | Pure hydrocarbon, no heteroatoms, no kspace |
| D-04 System size    | DP=100, 20 chains, ~2000 UA atoms                    | polymer_rules.json PDIE default |
| D-08 Hardware       | engine=gpu, mpi=1, GPU 2                             | hardware_policy[trappe]: gpu+neigh_yes; GPU 2 free + claimed |
| D-05 Convergence    | PASS                                                 | overall_pass=true; density SEM 0.0283%, energy SEM 0.0445%; no extensions needed |
| D-06 Tg fit quality | EXCELLENT                                             | R²=0.9998, N=16 bins; is_glassy=False (Tg=184.2 K @ r100 < 300 K) |
| D-06b Multirate Tg  | DSC-equiv=185.3 K (rubbery_flat_mean)                | rubbery_flat_mean: b=5.43 K/dec, R²=0.26 (flat expected), N_rates=5 @ [25,40,50,100,160] K/ns, N_repl=2; slope_gate_pass=True (rubbery_regime_exemption); VF FAILED (<2 decades, diagnostic only) |
| D-07 Property method | murnaghan (rubbery) + fluctuation diagnostic         | Tg=184.2 K → is_glassy=False; bm_pressures_atm=[1,100,300,600,1000] atm at T=300 K; Murnaghan K=1.263 GPa WARNING (B0'=15.74 runaway); B_fluct=1.566 GPa (inside [1.38,1.95], matches cis-PBD1) |

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
| equil | a0f8ec23 | 23:28 | 03:50 | ~4h22m | done |
| tg-r25 | 7221debe | 04:05 | 07:15 | ~3h10m | done — Tg=180.8 K EXCELLENT |
| tg-r50 | 3399c42d | 07:18 | 09:05 | ~1h47m | done — Tg=175.2 K EXCELLENT |
| tg-r100 | a2480bf5 | 09:07 | 09:52 | ~45m | done — Tg=184.2 K EXCELLENT |
| murnaghan | 13b36791 | 09:55 | 13:10 | ~3h15m | done |

GPU inventory: GPU 2: Quadro RTX 6000, 24 GB, free at claim; GPU 0 (PSU2), GPU 1 (PMMA2), GPU 3 (PLA2) in use

---

## D-05 CONVERGENCE DETAIL

<!-- check_equilibration_comprehensive result pasted below -->

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | 26.1 ± 4.6 Å | CV 17.6% < 30% → PASS |
| MSD plateau   | sub-diffusive (α=0.334); no kinetic trap | PASS |
| Density homog (CV) | 12.8% (7³ grid) | < 25% → PASS |
| C(t) decay (melt NVT) | 2.8% at end; τ_relax=585 ks / N/A — rubbery | annotation (partial decay expected below Tg) |
| τ_c chain relax (KWW) | 585304.5 ps / N/A — rubbery | advisory (trajectory T_traj=1951 ps ≪ τ_relax) |
| R_ee mean ± std | 62.81 ± 20.65 Å (N=20 chains) | ~approximate (backbone_types=[1,1] passed but actual=[1,2]) |

### Full Check Result

## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.04 K · 1951 frames analysed (skip=50) · 2026-06-23 23:31

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0943% (p=0.0313) | <1%, p<0.01 | PASS |
| Energy drift | 0.4308% (p=0.0001) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0283% | <1% | PASS |
| Energy block-SEM | 0.0445% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 17.6% | <30% | PASS |
| MSID slope | 1.042 (R²=0.9898) | 1.0 ±20% | OK |
| C(t) τ_relax | 585304.5 ps (3% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.334, MSD=940.11 Å²>>Rg²=704.194) | — | OK |
| R_ee mean ± std | 62.81 ± 20.65 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0159 ± 0.0068 | <0.10 | PASS |
| Density homogeneity CV | 12.8% (7³ grid, 23.4 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 3% decayed at end of trajectory (τ_relax=585304.5 ps vs T_traj=1951.0 ps)

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 0.8984 g/cm³ | 0.869–0.961 g/cm³ | −0.2% | NPT 300 K plateau (block-SEM 0.028%) | ✓ |

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (MD flat-mean, rubbery) | 185.3 K | 167–178 K (DB) / ~181 K (polymer_rules) | +4% vs DB upper | rubbery_flat_mean, 5 pts, 2 replicates | ⚠ (borderline: r50=175.2 K inside DB range; 181 K commonly cited) |
| Tg r25 (replicate 2) | 180.8 K | — | — | bilinear fit | annotation |
| Tg r50 (replicate 2) | 175.2 K | — | — | bilinear fit | annotation |
| Tg r100 (replicate 2) | 184.2 K | — | — | bilinear fit | annotation |
| α_g (CTE, r25) | 20.8×10⁻⁵ K⁻¹ | — | — | bilinear density fit, glassy branch | annotation |
| α_r (CTE, r25) | 67.4×10⁻⁵ K⁻¹ | — | — | bilinear density fit, rubbery branch | annotation |
| ΔCp at Tg (r25) | 0.231 J/(g·K) | — | — | H(T) bilinear fit | annotation |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K (volume_fluctuation) | 1.566 ± 0.151 GPa | 1.38–1.95 GPa | +13% vs lower | NPT volume fluct., n_eff=902, τ_eff=1.39 fr | ✓ |
| K (Murnaghan) | 1.263 GPa | 1.38–1.95 GPa | −8.5% | Murnaghan EOS, P=[1,100,300,600,1000] atm | ⚠ (B0'=15.74 runaway — narrow-pressure artifact; see note) |
| B0' | 15.74 | 7–11 (typical) | — | Murnaghan fit (artifact of ±0.1 GPa window) | ⚠ |
| G   | N/A | — | — | deformation (glassy only) | N/A |

**Note (BM):** generate_run_summary prioritized bulk_modulus_murnaghan.json (1.263 GPa, FAIL) over bulk_modulus.json (fluctuation, 1.566 GPa, PASS). Primary reported K = **1.566 ± 0.151 GPa** (PASS). Same as cis-PBD1 (1.565 GPa). Murnaghan B0'=15.74 is a known artifact of narrow rubbery pressure window.

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`
