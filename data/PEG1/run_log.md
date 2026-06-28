# Polyethylene glycol (PEG) Run PEG1 · 2026-06-20 → 2026-06-21
SMILES: `*CCO*`  |  FF: PCFF (Class II, EMC)  |  Charges: AM1-BCC  |  DP: 100  |  Chains: 10  |  GPU: 0
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=random (-1 requested; resolved seed not persisted by EMC, job=47fb86c4)  |  SEED_HOT=548980  |  SEED_COLD=N/A (nvt_production inherits from data file)
Plan: `data/PEG1/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved (round 1, deterministic auto-approve)  |  T_workflow_K: 300
Class: POXI (Polyoxide/Polyether), confidence=high | Member: PEO/PEG (exp Tg=206 K, exp ρ=1.12) → rubbery at 300 K → K via fluctuation path | Resources: 4 cores, MPI≤4, GPU 0, 32 GB, 48h max

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-00 Plan/critic    | deterministic plan, critic approved (round 1)        | POXI confidence=high → defaults transcribed verbatim; auto-approved by confidence gate |
| D-01 Force field    | PCFF (Class II, via EMC)                             | classify→POXI; EMC POXI routing = PCFF. NkepsuMbitou2025: PCFF Class II > GAFF2 for thermomechanical |
| D-02 Charges        | AM1-BCC                                              | polar polyether backbone |
| D-03 Electrostatics | PPPM (cutoff 12 Å)                                  | backbone heteroatoms (ether O) → PPPM |
| D-04 System size    | DP=100, 10 chains                                    | polymer_rules.json POXI default |
| D-08 Hardware       | foundation+r160+r640: engine=GPU pkg, MPI=4, GPU 0. r40 sweep: engine=KOKKOS, MPI=1, GPU 0 | KOKKOS full-offload (class2/kk+pppm/kk) flipped GREEN for pcff 2026-06-20, parity 0.000% vs GPU-pkg on energies+forces; ~7.9× faster. r40 rerun on KOKKOS per user request to speed the slowest sweep. Mixing engines across rates OK (bitwise-parity PES). |
| D-05 Convergence    | PASS                                                | overall_pass=true; density 1.0577 g/cm³ (0.22% vs exp 1.060). Warnings: C∞ backbone-type artifact (info); MSD slow-diffusion at DP=100 (info) |
| D-06 Tg fit quality | EXCELLENT (all 3 rates R²≥0.997) | Multirate: Tg_MD = 218.8 / 226.1 / 233.9 K @ 40/160/640 K/ns. Log-linear Tg=198.6+5.45·ln(Γ), R²=0.9996 → **Tg(5 K/ns)=207.4 K** (exp PEO 206 K, 0.7%). VF underconstrained (1.2 decades) → use log-linear. CTE (r40): α_g=16.5×10⁻⁵, α_r=58.5×10⁻⁵ K⁻¹; ΔCp=0.548 J/(g·K) |
| D-07 Property method | fluctuation (rubbery) | Tg=207.4 K < 300 → is_glassy=False; bm_pressures_atm=null → NPT volume-fluctuation path (no new sim; reads npt_production log) |

<!-- Add rows for non-routine decisions (parameter overrides, custom protocols, etc.) -->

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts) -->

## RECOVERY — tg-sweep attempt 1
- **Trigger:** run 255bb375 (rate 40 K/ns) failed exit 1: "Bond style class2 in data file differs from currently defined bond style harmonic; Incorrect args for bond coefficients"
- **Diagnosis:** generate_script emitted harmonic/amber FF styles (pair lj/charmm/coul/long, bond/angle harmonic, dihedral fourier, improper cvff, special_bonds amber) but the data file is PCFF Class II (bond style class2). The use_pcff:true lammps_flag did not propagate into the script's FF directives.
- **Action:** re-spawn tg-sweep-worker; explicitly thread use_pcff=True into generate_script params so PCFF Class II styles are emitted.
- **Outcome:** FF fixed (run 446fce1c emitted correct class2 styles), but the worker selected the wrong template — a single-T NPT density script (`run 100000`, one temperature) instead of the 440→100 K ramp. Output invalid as a Tg sweep. See attempt 2.

## RECOVERY — tg-sweep r40 attempt 2
- **Trigger:** run 446fce1c (rate 40 K/ns) "completed" but ran a single-temperature NPT (T 291–371 K, step 0–100k), not the multi-T cooling sweep. No per_t_structs.dump; .in header = "Run short NPT at a single T".
- **Diagnosis:** the retry worker, while applying the FF fix, generated the wrong script template (single-T density extraction). The r160/r640 workers used the correct ramp template (full 440→100 K, 18-step per_t dump) and are valid.
- **Action:** re-spawn tg-sweep-worker for rate 40 with explicit multi-T ramp requirement (T_start 440, T_end 100, T_step 20, 18 points, per_t_structs.dump) AND the class2 FF requirement; verify the .in has both a temperature loop and class2 styles before submitting.
- **Outcome:** ramp+FF verified (run cee21977) and started cleanly, but superseded — user requested KOKKOS for speed (see KOKKOS recovery below). cee21977 stopped at ~6%.

## RECOVERY — tg-sweep r40 KOKKOS engine (user-requested speedup)
- **Trigger:** user asked to rerun the sweep with KOKKOS (~7.9× faster, pcff parity GREEN 2026-06-20). Three sub-failures hit while wiring it:
  1. MCP run (1ec559c5): `run_lammps_script` has NO engine param — it launched the gpu-package binary (`/lammps-install/bin/lmp -sf gpu -pk gpu`) on a /kk deck → "Unrecognized pair style lj/class2/coul/long/kk ... KOKKOS not enabled in this binary". The engine=kokkos wiring claimed in hardware_policy is not exposed by the run tool.
  2. Manual launch v1: deck had `neighbor 2.0 bin/kk` (invalid — neighbor bin style takes no /kk suffix) → "Unknown neighbor argument bin/kk". Fixed → `neighbor 2.0 bin`.
  3. Manual launch v2: deck had `package kokkos gpu 1 comm no` (illegal — `package kokkos` has no `gpu N` keyword; GPU count is the CLI `-k on g 1`) → "Illegal package kokkos command". Fixed → `package kokkos neigh full comm no`.
- **Diagnosis:** (a) MCP run_lammps_script cannot select the KOKKOS binary; (b) the script_generator's kokkos deck over-suffixes `neighbor` and emits an illegal `package kokkos gpu N` line.
- **Action:** launch the KOKKOS binary directly (`/lammps-install-kokkos/bin/lmp -k on g 1 -sf kk`, mpi=1, GPU 0) via a manual wrapper (k40kok_run.sh) reusing the same sentinel/pid mechanism so Monitor works. Deck patched (neighbor + package lines). class2/kk + pppm/kk parity vs gpu-pkg = 0.000% (policy, 2026-06-20).
- **Outcome:** run k40kok started cleanly — read_data OK, Verlet set up, integrating (GPU 0 ~63%). Monitoring.
- **Measured throughput (same 7020-atom r40 deck, GPU 0, dt=1fs):** GPU-package mpi=4 = 13.56 ns/day (157 timesteps/s); KOKKOS mpi=1 full-offload = 37.77 ns/day (437 timesteps/s) → **2.79× actual** (timesteps/s identical ratio). NB: policy's ~7.9× was vs gpu-pkg at mpi=1; against our mpi=4 baseline the real gain is ~2.8×. Wall-clock r40 (9 ns): ~15.9 h → ~5.7 h (~10 h saved).

**Note for codebase (hardware-optimization branch):** (1) `run_lammps_script`/`run_lammps_chain` MCP tools need an `engine` arg to select the KOKKOS binary + emit `-k on g 1 -sf kk`; currently only gen_prompt/deck honor engine=kokkos. (2) script_generator kokkos path emits invalid `neighbor 2.0 bin/kk` and `package kokkos gpu 1 ...` — should be `neighbor 2.0 bin` and `package kokkos neigh full comm no`.

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Status |
|-------|----|-----------|--------|
| equil | ae9b7b4b | 2026-06-20 | done |
| tg-sweep r40 | 255bb375 | 2026-06-20 | failed (FF mismatch) |
| tg-sweep r40 (retry) | 446fce1c | 2026-06-20 | invalid (single-T template, not sweep) |
| tg-sweep r40 (attempt 2) | cee21977 | 2026-06-20 | stopped @6% (superseded by KOKKOS rerun) |
| tg-sweep r40 (KOKKOS via MCP) | 1ec559c5 | 2026-06-20 | failed (wrong binary: MCP ran gpu-pkg lmp on /kk deck) |
| tg-sweep r40 (KOKKOS manual) | k40kok | 2026-06-20 | done |
| tg-analysis (3 rates) | — | 2026-06-21 | done (Tg=207.4 K) |
| bulk-modulus (fluctuation) | — | 2026-06-21 | done (K=3.14 GPa) |
| tg-sweep r160 | f7979419 | 2026-06-20 | done |
| tg-sweep r640 | 8fcef190 | 2026-06-20 | done |

---

## D-05 CONVERGENCE DETAIL

<!-- Paste result["d05_markdown"] from check_equilibration_comprehensive here. -->

`check_equilibration_comprehensive` · T=300.13 K · 1951 frames (skip=50) · 2026-06-20 14:16 · **Overall: PASS**

Thermo: density drift 0.384% (PASS) · energy drift 0.694% (PASS) · density SEM 0.061% (PASS) · energy SEM 0.180% (PASS) · τ_eff 0.1%
Spatial: P2 nematic 0.0 (PASS) · density homogeneity CV 22.0% (<25% PASS)

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | CV 21.6% (chain–chain) | CV < 30% → PASS |
| MSD plateau   | trapped/subdiffusive (α=0.114) | INFO (DP=100 slow diffusion in 2 ns melt) |
| Density homog (CV) | 22.0% | < 25% → PASS |
| C(t) decay (melt NVT) | N/A (insufficient frames) | — |
| τ_c chain relax (KWW) | N/A | annotation only |
| R_ee mean ± std | N/A (not available from dump) | end_to_end_summary.json |
| C∞ | 346.7 (backbone-type detection artifact) | INFO |

---

## TIMING

| Worker | Submitted | Completed | Wall time | Throughput |
|--------|-----------|-----------|-----------|------------|
| Cell build | 06-20 00:24 | 06-20 00:31 | ~0h 7m | — |
| Equilibration (chain ae9b7b4b) | 06-20 00:33 | 06-20 14:16 | 13h 43m | ~12.9 ns/day (npt_production) |
| Tg sweep (3 rates) | 06-20 14:16 | 06-21 02:54 | 12h 38m | r40 KOKKOS 41.5 ns/day; r160/r640 GPU-pkg ~13.8 ns/day |
| Born / Deform / Murnaghan | — | — | N/A (rubbery → fluctuation path, no new sim) | — |
| **Total** | 06-20 00:24 | 06-21 03:05 | **~26h 41m** (incl. analysis) | |

Notes: r160 (f7979419) done 18:24, r640 (8fcef190) done 19:24 (GPU-package, sequential), r40 (k40kok) done 06-21 02:54 (KOKKOS rerun, ~5.7h). Born/Deform/Murnaghan not run — PEG is rubbery at 300 K, K from NPT volume fluctuations (reads npt_production.log).

GPU inventory (`nvidia-smi` at run start, 2026-06-20 00:24):
- GPU 0: NVIDIA A800 40GB, 40 GB, ~40 GB free (idle). All sims used GPU 0.

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.0577 ± 0.0006 g/cm³ | 1.007–1.113 g/cm³ (exp 1.060) | 0.22% | NPT 300K plateau | ✓ |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg        | 207.4 K (log-linear @5 K/ns) | 206 K (PEO exp) | 0.7% | multirate log-linear extrap (3 rates) | ✓ |
| α_g (CTE) | 16.5×10⁻⁵ K⁻¹  | ~15–25×10⁻⁵ K⁻¹ (typ.) | — | −a_glassy / ρ_mean_glassy (r40) | ✓ |
| α_r (CTE) | 58.5×10⁻⁵ K⁻¹  | ~60–80×10⁻⁵ K⁻¹ (typ.) | — | −a_rubbery / ρ_mean_rubbery (r40) | ✓ |
| ΔCp at Tg | 0.548 J/(g·K)   | ~0.5–0.8 J/(g·K) (typ.) | — | H(T) bilinear fit (r40, R²=0.999) | ✓ |
| cooling rate | 40/160/640 K/ns | ~10⁻⁷ K/ns (exp) | — | multirate (1.2 decades) | annotation |
| single-rate Tg | 218.8 (40) / 226.1 (160) / 233.9 (640) K | — | — | per-rate bilinear, all EXCELLENT | annotation |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 3.14 ± 0.12 GPa | — (no PEO K tabulated) | — | fluctuation (N_eff=428, τ_eff=0.12%, T=300.1 K) | — no exp. ref. (lit. ~3–4 GPa, plausible) |
| B0' | N/A     | 7–11 (typical) | —    | Murnaghan fit (rubbery only) — not run (bm_pressures null) | annotation |
| G   | N/A — rubbery | — | — | deformation (glassy only)               | N/A |
| E   | N/A — rubbery | — | — | deformation (glassy only)               | N/A |

Caveat: B_def cross-check unreliable (R²=0.025, expected for soft melt); slight V drift 0.38%; block-K scatter std 0.26 GPa. For a barostat-independent K, a Murnaghan pressure series would be more accurate (not in plan).

### D — Chain Structure

| Metric | Value | Status |
|--------|-------|--------|
| Rg mean ± std     | 19.82 Å (CV 21.6%, N=10 chains) | PASS (CV < 30%) |
| MSD plateau       | sub-diffusive / kinetically trapped (α=0.114, MSD_max=45.5 Å²) | INFO (DP=100 slow melt diffusion) |
| Density homog (CV)| 22.0% (7³ grid, 20.5 atoms/voxel) | PASS (< 25%) |
| C(t) decay (melt NVT) | N/A — insufficient frames | — |
| τ_c chain relax (KWW) | N/A | annotation only |
| R_ee mean ± std   | N/A (not available from dump) | — |

C∞ reported as 346.7 by the analysis — a backbone-type detection artifact (PEO C∞ ≈ 5–7); informational only, does not affect any reported property.

Simulation dir: `/home/alexzhao/PolyJarvis/data/PEG1/lammps/`
Outputs: `data/PEG1/raw/` — `run_summary.json`, `tg_multirate_result.json`, per-rate `tg_r{40,160,640}/`, `density.json`, `bulk_modulus.json`; figures in `data/PEG1/graphs/`
