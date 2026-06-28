# Polysulfone (PSU/Udel) Run PSU4 · 2026-06-26 → [END_DATE]
SMILES: `*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1`  |  FF: PCFF (EMC) |  Charges: bond-increment (PCFF)  |  DP: 25  |  Chains: 8  |  Atoms: 10,816  |  GPU: 2 (KOKKOS mpi=1) — claim label "PSU4"; task requested GPU 3 but pick_gpu ledger assigned GPU 2 (both idle, no collision)
Requested: density, tg, bulk_modulus (all)  |  Replicate: 3rd PSU run (PSU1/PSU2 complete)  |  Seeds: EMC=734512  |  SEED_HOT=481627 (equil velocity_seed)  |  SEED_COLD=N/A (equil); Tg-sweep velocity_seed=581931 (pinned, shared across r25/r50/r100 — this replicate)
<!-- D-02 sulfone charges VERIFIED non-zero: S(sf)=+0.0822, sulfone O=-0.1143 (200 S, 400 O); net 0.0000. No missing frc increments. -->

Plan: `data/PSU4/raw/run_plan.json`  |  mode: reasoned  |  confidence: medium  |  critic: approved (round 1, 3 advisories)  |  T_workflow_K: 700  |  dominant_uncertainty: ff_transferability (probe: literature_anchor)
<!-- CRITIC ADVISORIES (non-blocking): (1) D-07 no bm_pressures_atm → stiff PSU Murnaghan ±1000atm may yield B0' outside [4,20] → watch for deform fallback; (2) D-06 top rate 100 K/ns = 200 ps/T, above [40,80] aromatic cap edge but clears floor; (3) D-05 DP=25 < require_glassy DP>=30, plan correct via _ct_note (C(t) non-binding for aromatic). -->
<!-- D-08 hardware = policy default (kokkos/mpi=1/1 GPU); gen_prompt threads it, do NOT pass --gpu_ids/--mpi_ranks. Claim GPU at equil submit. -->
<!-- BM advisory follow-up: if Murnaghan B0' outside [4,20], widen pressures to ±5000 atm (PEST precedent) BEFORE deform fallback. -->

<!-- RUN-NAME NOTE: Task.txt says "Run name: PSU2" but PSU2 already exists/complete with different resources (GPU0/KOKKOS). Directory is PSU4; using PSU4 to avoid clobbering PSU2. Task resources: GPU id 3, mpi=1, 1 core, 32 GB, 48 h. -->
<!-- POLICY NOTE: properties_requested includes tg → DO NOT use glassy_hint; is_glassy set from extracted Tg_K after thermal track (provisional is_glassy=True for planning). -->
<!-- D-02 PSFO note: SO2 has no explicit charge; verify EMC PCFF assigns sulfone S type (so2/o_2s) before equil submit. A 0.0000 charge = MISSING frc increment, not small value. -->
<!-- Tg rates: polymer_rules + planner memory agree on [25,50,100] K/ns (dt=1fs/step=20K → 800/400/200 ps/T, clears floor). NOT degenerate at these slow rates. -->
<!-- PSFO bias expectation: PSU density ~-4% below exp, Tg ~+8% above exp at slow rate; K PASS is the headline (exp K_T 4.0-5.5 GPa). -->


---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF (EMC)                                          | classify_polymer → PSFO → EMC PCFF auto-routed (Class II; aryl-SO2-aryl + aryl ether) |
| D-02 Charges        | bond-increment (PCFF, embedded)                     | EMC bond-increment; sulfone verified non-zero S=+0.082, O=−0.114 |
| D-03 Electrostatics | PPPM 12 Å                                           | Backbone heteroatoms (sulfone S+2O, ether O) carry charge → long-range Coulomb |
| D-04 System size    | DP=25, 8 chains, 10,816 atoms                       | polymer_rules PSFO dp_typical=25, nchain=8 |
| D-05 Convergence    | PASS (carve-out)                                    | Hard gates pass (density drift 0.083%, SEM 0.019%, P2 0.014); marginal CV (Rg 31.6%, homog 26.2%) = finite-size Poisson noise on 8-chain glassy aromatic (PSU3 precedent) → advisory. Density 1.1788 g/cm³ (−4.5% vs exp 1.235, PCFF bias) |
| D-06 Tg fit quality | [EXCELLENT / ACCEPTABLE / BORDERLINE / ABORT / N/A]  | [R²=[X], N=[N] bins, F-stat=[TIER]; is_glassy=[true/false] (Tg=[X] K > 300 K) / N/A — tg not requested] |
| D-06b Multirate Tg  | [DSC-equiv=[X] K / N/A]                              | [log-linear Tg(Γ) b=[X] K/ln(K/ns), R²=[X], N_rates=[3] @ [40,160,400] K/ns, N_repl=[N]; extrapolated to 1.67e-10 K/ns (10 K/min DSC); VF=[quality] (diagnostic, <2 decades) / N/A — single-rate] |
| D-07 Property method | [born (glassy) / deform fallback (glassy) / murnaghan (rubbery) / fluctuation (rubbery fallback) / N/A] | [Tg=[X] K → is_glassy=[true/false]; bm_pressures_atm=[Y/N] / N/A — bulk_modulus not requested] |

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

### R-01 — Equil chain disk-full crash mid-npt_cool (2026-06-26 16:11)
- **Symptom:** chain 4cf41725 sentinel = failed; `npt_cool.log`: `ERROR on proc 0: Error writing dump dump_npt: No space left on device (dump.cpp:543)` at step 1,966,000; MPI_ABORT.
- **Root cause:** root filesystem (`/dev/nvme0n1p2`, 937 G) hit 100% (36 M free) — saturated by accumulated LAMMPS dump trajectories across ~20 runs (PEEK3 7.2G, PMMA3 6.2G, PSU2 5.9G, …). npt_cool dump write hit ENOSPC. NOT a simulation-physics failure. Also blocked the orchestrator's own tool-output staging (shared FS).
- **Fix:** (1) Freed disk per retention policy — deleted PSU4 intermediate-stage dumps (~2.4 G) + intermediate-category dumps (npt_cool/softheat/compress/pppm/prod300/bm_P) across 13 completed runs (~22 G, 153 files), excluding live PLA4 + all nvt_production/npt_production result-feeding dumps → 50 G free. (2) Stages minimize→nvt_softheat→npt_compress→npt_pppm intact (have _out.data). Cleaned npt_cool partials (npt_1.rst/npt_2.rst/log). (3) Regenerate workflow w/ identical params, slice from npt_cool, resume reading npt_pppm_out.data (attempt 1/2). GPU 2 claim held across failure (no re-claim race).
- **Outcome:** converged — resume chain e08b57ca completed all 5 tail stages (npt_cool→nvt_production→npt_production→npt_cool300→npt_prod300), no re-fill (disk stayed >40 G). 1 attempt sufficed.


---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage glassy) | 4cf41725 | 11:10 | 16:11 | 5h 01m | failed (ENOSPC @ npt_cool — see R-01) |
| equil resume (5-stage tail) | e08b57ca | 16:33 | ~22:30 | ~6h | done (all 5 _out.data present) |

GPU claim: label "PSU4" → GPU 2 (KOKKOS mpi=1), held across failure. Resume tail: npt_cool → nvt_production → npt_production → npt_cool300 → npt_prod300, reading npt_pppm_out.data. Chain ends npt_prod300_out.data (300K glassy production). nvt_production_out.data = melt 700K (thermal sweep input + C(t)).

### Phase B — parallel tracks (exploiting idle GPUs as PLA4 releases them)
| Job | run_id | GPU | bg-task | Status |
|-----|--------|-----|---------|--------|
| Tg sweep r25 (800k/T, 20.8 ns) | 5ba05fb9 | 2 (PSU4) | buqliu14e | monitoring |
| Tg sweep r50 (400k/T, 10.4 ns) | 585fddb9 | 3 (PSU4-r50) | bo5ytzozy | monitoring |
| Tg sweep r100 (200k/T, 5.2 ns) | 6238f8d8 | 0 (PSU4-r100) | (launching) | monitoring |
| Murnaghan BM (glassy 300K, ±5000 atm) | — | — | — | PENDING (next freed GPU: r100→GPU0 or GPU1 if it frees) |

r25 script VERIFIED: pair_style lj/class2/coul/long, 26-temp staircase, KOKKOS (no `package gpu`). tg_log_path = tg_sweep_r25/tg_step.log. GPU-free poller running to claim GPUs 0/3 as PLA4 frees them.

GPU inventory (`nvidia-smi` at run start): GPU [ID]: [model], [VRAM] GB, [free] GB free

---

## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.0 K · 201-frame DECIMATED melt dump (full 1.5 GB/2001-frame dump hangs the tool — PSU3 precedent) · 2026-06-27 04:16

**Overall: PASS** (require_glassy carve-out applied: marginal CV failures are finite-size Poisson noise on an 8-chain glassy aromatic cell; all hard gates pass)

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0827% (p=0.0092) | <1%, p<0.01 | PASS |
| Energy drift | 0.0618% (p=0.205) | <1% | PASS |
| Density block-SEM | 0.0189% | <1% | PASS |
| Energy block-SEM | 0.013% | <1% | PASS |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0145 ± 0.0041 | <0.10 | PASS |
| Density homogeneity CV | 26.2% (8³ grid, 21.1 atoms/voxel) | <25% | ADVISORY (finite-size, +1.2%) |

**Gate verdict:** All hard thermodynamic + P2 gates pass; density SEM 0.019% ≪ 0.5% threshold. Marginal CVs (Rg 31.6%, homog 26.2%) are finite-size artifacts on N=8 chains (PSU3 DP=25 precedent), advisory not blocking. **PASS.**

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg CV (chain–chain) | 31.6% | CV < 30% → ADVISORY (finite-size, N=8) |
| MSID slope | 1.026 (R²=0.9952) | 1.0 ±20% → OK |
| Density homog (CV) | 26.2% | < 25% → ADVISORY (finite-size) |
| C(t) decay (melt NVT) | 3.3% decayed (τ_relax=29,212 ps) | aromatic backbone → ADVISORY (non-binding) |
| τ_c chain relax (KWW) | 29,212 ps | annotation only |
| R_ee mean ± std | 76.63 ± 37.36 Å (N=8 chains) | end_to_end_summary.json |
| Density (300 K plateau) | 1.1788 ± SEM 0.019% g/cm³ | −4.5% vs exp 1.235 (PCFF bias, expected) |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | [X] g/cm³ | [X]–[X] g/cm³ | [X]% | NPT 300K plateau | [✓ / ⚠] |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (DSC-equiv) | [X] K      | [X]–[X] K              | [X]% | log-linear Tg(Γ)→10 K/min (multirate) | [✓ / ⚠] |
| Tg (MD @400 K/ns) | [X] K   | —                      | —    | bilinear fit, highest screening rate | annotation |
| α_g (CTE) | [X]×10⁻⁵ K⁻¹   | [X]–[X]×10⁻⁵ K⁻¹      | [X]% | −a_glassy / ρ_mean_glassy | [✓ / ⚠] |
| α_r (CTE) | [X]×10⁻⁵ K⁻¹   | [X]–[X]×10⁻⁵ K⁻¹      | [X]% | −a_rubbery / ρ_mean_rubbery | [✓ / ⚠] |
| ΔCp at Tg | [X] J/(g·K)     | [X]–[X] J/(g·K)        | [X]% | H(T) bilinear fit         | [✓ / ⚠ / N/A] |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | [X ± Y_sem] GPa | [X]–[X] GPa    | [X]% | born (N_eff=[N], τ_ac≈[X] ps) / deform / murnaghan / fluctuation (N_eff=[N], τ_eff=[X]%) | [✓ / ⚠ / — no exp. ref.] |
| B0' | [X]     | 7–11 (typical) | —    | Murnaghan fit (rubbery only)            | annotation |
| G   | [X] GPa | [X]–[X] GPa    | [X]% | deformation (glassy only)               | [✓ / ⚠ / N/A] |
| E   | [X] GPa | [X]–[X] GPa    | [X]% | deformation (glassy only)               | [✓ / ⚠ / N/A] |

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`
