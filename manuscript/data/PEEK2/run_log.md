# PEEK (Poly(ether ether ketone)) Run 2 · 2026-06-22 → 2026-06-23
SMILES: `*Oc1ccc(Oc2ccc(C(=O)c3ccc(cc3)*)cc2)cc1`  |  FF: PCFF  |  Charges: bond-increment  |  DP: 32  |  Chains: 10  |  Atoms: 10900  |  GPU: 2
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=274348  |  SEED_HOT=55628  |  SEED_COLD=N/A (nvt_production inherits)
Plan: `/home/arz2/PolyJarvis/data/PEEK2/raw/run_plan.json`  |  mode: reasoned  |  confidence: high  |  critic: approved (2 rounds)  |  T_workflow_K: 770.0

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                                                | classify_polymer → PKTN (class 19) → EMC auto-routed pcff |
| D-02 Charges        | embedded in FF (bond-increment)                     | EMC class-II PCFF bond-increment charges |
| D-03 Electrostatics | PPPM                                                | aromatic ether/ketone heteroatoms → PPPM, cutoff 12 Å |
| D-04 System size    | DP=32, 10 chains, 10900 atoms                        | polymer_rules.json PKTN defaults; density_initial=0.66 |
| D-05 Convergence    | PASS (no extensions)                                  | density=1.194 g/cm³ (−5.5% vs 1.263, same as PEEK1); C(t) advisory-only (aromatic PKTN); thermo+spatial PASS |
| D-06 Tg fit quality | r40: EXCELLENT (Tg=523.6 K, R²=0.9967); r160: POOR (Tg_extracted=522.3 K, c=None degenerate); r400: POOR (Tg_extracted=480.0 K, c=None degenerate) | r40 and r160 extractors agree closely (~523 K). r400 degenerate fit (c=None) returns artifact 480 K — inverse-rate direction is a fitting artifact, not physical. Only r40 passes ≥ACCEPTABLE gate. is_glassy=True from plan exp-Tg (r400 fit degenerate; experimental PEEK Tg=418 K >> 300 K) |
| D-06b Multirate Tg  | single-rate fallback; Tg_MD = 523.6 K (r40 only)    | < 2 ACCEPTABLE registry rows → skip log-linear aggregation; report r40 Tg directly. No DSC extrapolation possible; Tg_MD=523.6 K is the best available estimate (N_rates=1 @ 40 K/ns) |
| D-07 Property method | Murnaghan (glassy primary, 300 K, ±1000 atm) → K=4.871 ± 0.026 GPa | fit_converged=True; B0'=11.32 (within [4,20]); R²=0.99995; K within exp [4.0–5.8 GPa]; no deform fallback needed |

<!-- Add rows for non-routine decisions (parameter overrides, custom protocols, etc.) -->

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts) -->

### R-01: Equilibration chain 2a790dda — MPI_Init failure (OpenMPI prefix)

**Stage:** equil (minimize, stage 1)  
**Error:** `OPAL_PREFIX=/home/arz2/openmpi` set in chain wrapper, but that path doesn't exist on this machine. The Kokkos binary links against system OpenMPI (`/lib/x86_64-linux-gnu/libmpi.so.40`) and needs `OPAL_PREFIX=/usr`.  
**Root cause:** server.py `OPENMPI_PREFIX` defaulted to `/home/arz2/openmpi` (nonexistent); the binary called MPI_Init → opal_init failure before any LAMMPS output.  
**Fix:** Patched `server.py` lines 79–81 to fall back to `/usr` when `/home/arz2/openmpi` is absent. Wrote manual recovery chain script `/tmp/polyjarvis/chain_peek2_r1.sh` with `OPAL_PREFIX=/usr` hardcoded; launched at 01:12 EDT.  
**Outcome:** converged — minimize log writing correctly (1:12 EDT)

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage kokkos) | peek2_r1 | 01:12 | 14:48 | 13h 36m | done |
| tg_sweep (npt_tg_step, r40)  | (manual/mcp) | 2026-06-23 | ~23:00 | ~9h | done |
| tg_sweep (npt_tg_step, r160) | 76ba421f | 2026-06-23 14:11 | ~16:30 | ~2h 20m | done |
| tg_sweep (npt_tg_step, r400) | ee25d295 | 2026-06-23 | 2026-06-23 | ~45m | done |
| bm_murnaghan (±1000 atm, 300K) | 89b89dd8 | 2026-06-23 | 2026-06-23 | — | done |

GPU inventory (`nvidia-smi` at run start): GPU 2: RTX 6000 24GB, 24200 MiB free  
Murnaghan params: glassy 300K, ±1000 atm (5 points), 0.5 ns/point, engine=kokkos, mpi=1

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=299.91 K · 1951 frames analysed (skip=50) · 2026-06-22 14:50

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0466% (p=0.0946) | <1%, p<0.01 | PASS |
| Energy drift | 0.0039% (p=0.9112) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0172% | <1% | PASS |
| Energy block-SEM | 0.0076% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 14.3% | <30% | PASS |
| MSID slope | 1.097 (R²=0.9964) | 1.0 ±20% | OK |
| C(t) τ_relax | 23803674.5 ps (2% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.318, MSD=1860.39 Å²>>Rg²=1401.964) | — | OK |
| R_ee mean ± std | 95.12 ± 27.29 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0267 ± 0.0075 | <0.10 | PASS |
| Density homogeneity CV | 22.9% (8³ grid, 21.3 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 2% decayed at end of trajectory (τ_relax=23803674.5 ps vs T_traj=1951.0 ps)

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.194 g/cm³ | 1.20–1.33 g/cm³ | −0.5% (just below lower bound) | NPT 300K plateau | ⚠ |

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (DSC-equiv) | N/A | 400–440 K | — | single-rate fallback; no log-linear fit (<2 valid rates) | N/A |
| Tg (MD @40 K/ns) | 523.6 K | 400–440 K | +18.5% above 440 K | bilinear EXCELLENT, R²=0.997; expected MD overestimate | ⚠ |
| α_g (CTE) | 1.97×10⁻⁴ K⁻¹ | — | — | −a_glassy / ρ_mean_glassy (r40 sweep) | annotation |
| α_r (CTE) | 4.27×10⁻⁴ K⁻¹ | — | — | −a_rubbery / ρ_mean_rubbery (r40 sweep) | annotation |
| ΔCp at Tg | 0.092 J/(g·K) | — | — | H(T) bilinear fit | annotation |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 4.871 ± 0.026 GPa | 4.0–5.8 GPa | 0% (within range) | Murnaghan NPT ±1000 atm, 300 K, R²=0.99995 | ✓ |
| B0' | 11.32 | 7–11 (typical) | — | Murnaghan fit | annotation |
| G   | N/A | — | — | deformation not run | N/A |
| E   | N/A | — | — | deformation not run | N/A |

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 39.8 h  |  **GPU**: 39.8 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PEEK2/lammps/**/*.log` (Born stages excluded); reproducible via `manuscript/gen_table_compute_cost.py`.
