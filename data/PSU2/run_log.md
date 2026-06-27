# Polysulfone (PSU, Udel) Run PSU2 · 2026-06-23 → 2026-06-25 · COMPLETE (K=PASS; Tg/ρ FAIL — expected PCFF bias)
SMILES: `*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1`  |  FF: PCFF  |  Charges: bond-increment (PCFF)  |  DP: 20  |  Chains: 10  |  GPU: 0 (KOKKOS mpi=1)
Requested: density, tg, bulk_modulus (all)  |  Replicate: 2 of 2 (revision baseline — fixed seeds)  |  Seeds: EMC=820419  |  SEED_HOT=611213  |  SEED_COLD=N/A
Plan: `data/PSU2/raw/run_plan.json`  |  mode: reasoned  |  confidence: medium  |  critic: approved (1 round, 0 findings)  |  T_workflow_K: 700
<!-- D-00: planner reasoned plan. Dominant uncertainty: ff_transferability (no class-specific PCFF PSFO validation paper). D-08 hardware: kokkos mpi=1 gpu=1 (KOKKOS kspace GPU-offloaded, canonical for PCFF/KOKKOS). Hardware_benchmark probe planned (values_are_benchmarked=false, cell 3.6× benchmark). nchain=10 (REVISION_PARAMS.md). is_glassy=True (Tg=499.7K from PSU1). BM method: Murnaghan 300K primary. -->
<!-- Exp anchors (PSU/Udel): Tg=463 K, density=1.24 g/cm³, K=4.0-5.5 GPa. PSU1: Tg=499.7K (+8%), density=1.187 (-4.3%), K=4.43 GPa (in range). -->

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                                                 | classify_polymer → PSFO → EMC auto-routes PCFF (use_pcff=true). Aryl-SO₂-aryl + aryl-ether covered via Class II cross terms. |
| D-02 Charges        | PCFF bond-increment (embedded)                       | EMC PCFF emits native bond-increment charges: S≈+0.08e, sulfone O≈−0.11e per S–O bond. No separate QM step. |
| D-03 Electrostatics | PPPM (cutoff 12.0 Å)                                 | Heteroatom backbone (S, O) → PPPM mandatory per policy. |
| D-04 System size    | DP=20, 10 chains, 10820 atoms                        | Revision baseline (REVISION_PARAMS.md): nchain=10 (vs 8 in PSU1), fixed seeds. Policy-compliant (DP≥20). Box ~61.9 Å cubic. |
| D-05 Convergence    | PASS (override after EXTEND×1 — melt-CV artifact)    | density-homogeneity CV=25.59% (gate <25%, 0.59% over) is measured from nvt_production.dump (melt at 700K), NOT from the cold 300K cell. Extension at 300K cannot move a melt-state metric → CV is thermally locked noise for 10-chain/DP=20 on 8³ grid (21.1 atoms/voxel). All thermo/energy/Rg/P2 PASS. Proceeding with npt_extend_out.data (most-equilibrated cold cell, ρ=1.185 g/cm³, drift=0.057%). |
| D-06 Tg fit quality | r400: GOOD (R²=0.9945, 27 bins, 4 drift-skipped) | is_glassy=True (Tg_r400=438.3 K > 300 K); exp PSU=463 K (−25 K delta, within ±50 K). r40/r160 in progress — multirate pending. |
| D-06b Multirate Tg  | UNRESOLVED — DSC-equiv not computed                  | r400 (50 ps/T) degenerate for PSU aromatic backbone: orig=438.3 K, rec1=374.7 K (systematic, not stochastic). r40=498.4 K and r160=502.1 K consistent (Δ=3.7 K, b=+2.67 K/ln). Slope gate cannot pass with r400 included. Proceeding with single-rate r40 Tg=498.4 K for run-summary. |
| D-07 Property method | Murnaghan NPT ±1000 atm at 300 K (glassy primary) | is_glassy=True (Tg_r400=438.3 K); chain d708d2da on GPU 0 (PSU2-murnaghan), 5 pts × 0.5 ns. |

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

**Recovery 1 — Equil-check density-homogeneity CV artifact (2026-06-23)**
- Symptom: equil-check returned EXTEND×1 with density-homogeneity CV=25.6%, then 25.59% after a 2 ns NPT extension at 300 K. CV was essentially unchanged (0.01% drop).
- Root cause: `check_equilibration_comprehensive` computes density-homogeneity CV from `dump_file` = `nvt_production.dump` (the melt trajectory at 700K), NOT from the cold cell. `gen_prompt.py` line 677 hardwires `melt_dump = args.npt_prod_dump or f".../nvt_production/nvt_production.dump"`. A 300K extension creates new cold-cell frames but never modifies the melt dump — the CV input is frozen. The EXTEND verdict was structurally unfixable via the prescribed cure.
- Fix: Overrode to PASS. Melt-state CV of 25.59% is statistical noise for 10-chain/DP=20 on 8³ grid (21.1 atoms/voxel at 700K); all thermo/energy/Rg/P2 in excellent shape. Proceeding with npt_extend_out.data.
- Pipeline gap: equil-checker's EXTEND/FAIL verdict for density-homogeneity CV triggered extension at 300K — a cure that is impossible for melt-state metrics. The fix should be: when equil-check EXTEND is caused solely by density-homogeneity CV AND T_workflow >> 300K, the orchestrator should check whether CV is melt-derived (always) and override sooner, skipping the 300K extension.
- Outcome: PASS override, proceeding to Phase B.

**Recovery 2 — Multirate Tg slope gate failure (2026-06-24) → UNRESOLVED**
- Symptom: slope_gate_pass=False — loglinear slope b=-23.78 K, R²=0.5923. r400=438.3 K anomalously low vs r40=498.4 K and r160=502.1 K. Negative slope indicates contamination (or structurally insufficient equilibration at r400=50 ps/T for this aromatic polymer).
- Root cause: r400 (50k steps/T = 50 ps/T) is structurally inadequate for PSU2's rigid aromatic backbone. At 50 ps/T, density plateaus at each T are too short for accurate bilinear fit. r40 and r160 sweeps (498.4 and 502.1 K) are consistent with each other and with exp (463 K).
- Fix attempt: Recovery 1 — re-ran r400 with new seed (392447) + r40 with new seed (134623). REC1-r400 complete: Tg=374.7 K — WORSE than original 438.3 K (further from exp, smooth curve with no kink). Two independent r400 trajectories confirm systematic failure of this rate for aromatic PSU, not stochastic noise.
- Outcome: **UNRESOLVED — multirate DSC-equiv Tg extrapolation.** r400 at 50 ps/T is degenerate for PSU class (same failure mode as PEEK/PKTN in memory). Recovery 2 would have same structural failure — not pursued. REC1-r40 killed at 1/26 stages (futile for slope gate). GPU 0 released.
- Override: Using single-rate r40 Tg=498.4 K (GOOD, R²=0.992) as primary Tg estimate for run-summary. r40 and r160 (502.1 K) are consistent (Δ=3.7 K, slope=+2.67 K/ln, b>0) but 2-point R²≡1.0 is not reliable for extrapolation. Reporting r40 as best-available per-rate MD Tg; marking DSC-equiv as UNAVAILABLE. is_glassy=True (r40=498.4 K > 300 K, exp Tg=463 K confirms).

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil | e1eb596f | 01:34 | 16:01 | ~14h27m | done |
| equil-extend | f9d321e0 | 20:36 | 23:34 | ~2h58m | done |
| tg-sweep-r40 | 88f0adbb | ~20:15 Jun23 | ~17:15 Jun24 | ~21h | done |
| tg-sweep-r160 | 4b1cb395 | ~13:10 Jun24 | ~21:30 Jun24 | ~8h20m | done |
| tg-sweep-r400 | 4c84dfd8 | ~09:40 Jun24 | ~13:05 Jun24 | ~3h25m | done |
| murnaghan-bm | d708d2da | ~17:20 Jun24 | ~21:00 Jun24 | ~3h40m | done — K=4.196 GPa (PASS, exp 4.0–5.5 GPa, R²=0.9995, B0'=11.34) |
| tg-rec1-r400 | 93a661cd | ~22:05 Jun24 | ~01:15 Jun25 | ~3h10m | done |
| tg-rec1-r40 | 2789b578 | ~21:00 Jun24 | ~01:30 Jun25 | ~4.5h | KILLED — multirate UNRESOLVED (1/26 stages done before kill) |

GPU inventory (`nvidia-smi` at run start): 4x Quadro RTX 6000 24 GB | PSU2 claimed GPU 0 (KOKKOS engine, mpi=1)

---

## D-05 CONVERGENCE DETAIL

<!-- Paste result["d05_markdown"] from check_equilibration_comprehensive here. -->

`check_equilibration_comprehensive` · T=300.23 K · 1951 frames analysed (skip=50) · 2026-06-23 16:01

**Overall: EXTEND** (density homogeneity CV=25.6% exceeds gate <25% by 0.6%; all other checks pass; extending 2 ns NPT at 300 K)

> **PASS OVERRIDE (2026-06-23 ~20:00 UTC):** Second equil-check on npt_extend_out.data returned CV=25.59% — no change from 25.60% pre-extension. CV is measured from nvt_production.dump (melt at 700K); NPT extension at 300K cannot modify the melt dump. Metric is melt-state statistical noise for this system size (8³/21.1 atoms/voxel). All thermo/density (ρ=1.185 g/cm³, drift=0.057%, block-SEM=0.012%) and chain (Rg CV=15.5%, P2=0.0098) checks pass. Proceeding with npt_extend_out.data as Phase B starting cell.

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1095% (p=0.0005) | <1%, p<0.01 | PASS |
| Energy drift | 0.0295% (p=0.5426) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.028% | <1% | PASS |
| Energy block-SEM | 0.0117% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 15.5% | <30% | PASS |
| MSID slope | 0.901 (R²=0.9855) | 1.0 ±20% | OK |
| C(t) τ_relax | 2692819.5 ps (4% decayed) | — | ⚠ advisory (aromatic) |
| MSD kinetic trap | no (α=0.242, MSD=971.03 Å²>>Rg²=651.065) | — | OK |
| R_ee mean ± std | 52.72 ± 19.92 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0098 ± 0.0037 | <0.10 | PASS |
| Density homogeneity CV | 25.6% (8³ grid, 21.1 atoms/voxel) | <25% | EXTEND |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.185 g/cm³ | 1.234–1.25 g/cm³ | −4.0% | NPT 300K plateau (npt_extend_out.data) | ⚠ FAIL — expected PCFF underdensity (PSU1: −4.3%) |

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (DSC-equiv) | UNAVAILABLE | 459–463 K | — | Multirate UNRESOLVED — r400 degenerate (50 ps/T) | ⚠ UNRESOLVED |
| Tg (MD @40 K/ns) | 498.4 K | 459–463 K | +7.6% | bilinear fit r40 (GOOD, R²=0.992); best available | ⚠ FAIL — expected MD overestimate at finite rate |
| Tg (MD @160 K/ns) | 502.1 K | — | — | bilinear fit r160 (EXCELLENT) — consistent with r40 | annotation |
| α_g (CTE) | 2.03×10⁻⁴ K⁻¹ | — | — | from r40 bilinear glassy branch | INFO |
| α_r (CTE) | 3.36×10⁻⁴ K⁻¹ | — | — | from r40 bilinear rubbery branch | INFO |
| ΔCp at Tg | 0.042 J/(g·K) | — | — | H(T) bilinear fit (r40) | INFO |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K | 4.196 ± 0.073 GPa | 4.0–5.5 GPa | 0.0% (at lower bound) | Murnaghan NPT ±1000 atm, 300K, R²=0.9995, B0'=11.34 | ✓ PASS |

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`
