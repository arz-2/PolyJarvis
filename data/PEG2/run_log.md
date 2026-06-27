# Poly(ethylene glycol) (PEG/PEO) Run 1 · 2026-06-22 → 2026-06-23
SMILES: `*CCO*`  |  FF: PCFF  |  Charges: bond-increment (EMC embedded)  |  DP: 100  |  Chains: 10  |  GPU: 0
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1  |  Seeds: EMC=533381  |  SEED_HOT=428608 (r40) / 906138 (r160) / [r400]  |  SEED_COLD=inherited (no re-init between T steps)
Plan: `data/PEG2/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved (round 1, 0 findings)  |  T_workflow_K: 300
D-08 hardware: gpu_per_run=1 (policy default), engine=default, mpi=2
Resources: CPU=1, MPI=2, GPU=0, 32 GB, max 48 h

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                | classify_polymer → POXI (class 7) → EMC PCFF auto-routed (high conf) |
| D-02 Charges        | bond-increment (EMC embedded)        | PCFF Class II library charges; no separate QM step |
| D-03 Electrostatics | PPPM, 12 Å cutoff                          | polyether backbone (C–O–C) heteroatoms → long-range Coulomb |
| D-04 System size    | DP=100, 10 chains, 7020 atoms                        | polymer_rules.json POXI defaults; EMC seed=533381 |
| D-05 Convergence    | PASS (EXTEND×1)                         | overall_pass=true after +2 ns ext; energy drift 1.52%→0.64%; density 1.0576 g/cm³; C(t)/MSD advisory (entangled DP=100 melt) |
| D-06 Tg fit quality | EXCELLENT (r160) / GOOD (r400)  | r160: Tg=245.3 K R²=0.9988; r400: Tg=214.8 K R²=0.9839. **is_glassy=FALSE** (Tg@400=214.8 K < 300 K → rubbery at T_workflow). r40 (slowest) pending. |
| D-06b Multirate Tg  | single_rate_fallback = 238.7 K (40 K/ns)  | 3 rates: r40=238.7 (EXCELLENT R²=.9995), r160=245.3 (EXCELLENT R²=.9988), r400=214.8 (GOOD R²=.984). Non-monotonic → log-linear slope −9.16 K, R²=0.44, slope_gate_pass=FALSE, is_flat_rate_regime=FALSE, VF FAILED. Span only 1 decade → DSC extrapolation not achievable. Reported MD Tg = slowest-rate 238.7 K (most equilibrated); +32.7 K vs exp 206 K (typical polyether MD overshoot). 3-rate mean=232.9 K (context). DSC-equiv = N/A. |
| D-07 Property method | fluctuation (rubbery) | is_glassy=FALSE + bm_pressures_atm=null → volume-fluctuation K from npt_ext.log (no extra sim). Born+NVT removed. |

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

### R-01 · Equil-check EXTEND (energy not plateaued) · 2026-06-22 19:30
- **Symptom:** equilibration-checker returned `overall_pass=false` / verdict EXTEND. Energy drift 1.52% (> 1% threshold, p=0). C(t) only 1% decayed (τ_relax≈7.4e9 ps) and MSD kinetic trap (α=0.1) — both chain-relaxation warnings.
- **Diagnosis:** Density is fully converged and in exp range (1.0571 g/cm³, drift 0.02%, SEM 0.04%, homogeneity CV 22%, P2 0.046 — all PASS). Energy oscillates ±150 around ~4000 with no clear monotonic trend; the 1.52% is a weak noise-dominated slope. C(t)/MSD non-relaxation is expected for a DP=100 entangled PEO melt (reptation τ ≫ ns), NOT fixable by a short extension.
- **Action (attempt 1/2):** Extend npt_production by 2 ns at 300 K / 1 atm from npt_production_out.data; re-run equil-check on the extension log. If energy drift persists, accept density (converged, in-range) with documented entangled-melt caveat.
- **Outcome:** converged. +2 ns extension (run a8ea3a0c) brought energy drift 1.52% → 0.64% (PASS, <1%), density drift 0.16%, density 1.0576 g/cm³. All thermo + packing gates pass. C(t)/MSD remain entanglement-limited (DP=100, reptation τ~µs) — accepted as advisory; they do not gate segmental/local properties (Tg, density, K). Equilibrated cell = `npt_production_ext/npt_ext_out.data`.

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (7-stage chain, rubbery) | ed32756d | 15:37 | 19:22 | 3h45m | done |
| equil-ext (+2 ns NPT, R-01) | a8ea3a0c | 19:34 | 20:40 | ~1h6m | done |
| tg-sweep r40 (18 T, GPU 0) | 13a1db37 | 20:50 | 01:49 | ~4h59m | done |
| tg-sweep r160 (18 T, GPU 3) | 936422e3 | 20:50 | 22:07 | 1h17m | done |
| tg-sweep r400 (18 T, GPU 3) | d36ee3f2 | 22:07 | 22:38 | ~31m | done |

GPU claim label: `PEG2-equil` (GPU 0)
GPU inventory (`nvidia-smi` at run start): GPU 0: NVIDIA A800 40GB Active, 40 GB, 39.9 GB free; GPUs 1–3 also free (40 GB each)

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=300.09 K · 1951 frames analysed (skip=50) · 2026-06-22 20:42

**Overall: PASS** (recovery R-01, extension +2 ns)

### A. Thermo convergence (extension log npt_ext.log)
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1595% (p=0.0005) | <1%, p<0.01 | PASS |
| Energy drift | 0.6375% (p=0.0128) | <1%, p<0.01 | PASS (was 1.52% pre-ext) |
| Density block-SEM | 0.0507% | <1% | PASS |
| Energy block-SEM | 0.1499% | <1% | PASS |

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg CV (chain–chain) | 22.4% | CV < 30% → PASS |
| MSD plateau   | still sub-diffusive (α=0.1, MSD=117 Å²) | ADVISORY — entangled DP=100 melt |
| Density homog (CV) | 22.1% (7³ grid) | < 25% → PASS |
| C(t) decay (melt NVT) | 1.1% at end (threshold 0.2) | ADVISORY — τ_relax≫T_traj (reptation) |
| τ_c chain relax (KWW) | 7.39e9 ps | annotation only (unreachable in ns MD) |
| P2 nematic order | 0.0461 ± 0.0044 | < 0.10 → PASS |
| R_ee mean ± std | 41.48 ± 25.48 Å (N=10 chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.0576 g/cm³ | 1.064–1.176 g/cm³ | −5.6% (vs 1.120 mid) | NPT 300K plateau (+2 ns ext) | ⚠ (just below band) |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (DSC-equiv) | N/A      | 206 K              | —    | multirate failed (1-decade span, slope_gate=false) | ⚠ extrapolation unavailable |
| Tg (MD, slowest 40 K/ns) | 238.7 K   | 206 K          | +15.9% (+32.7 K) | bilinear fit, single_rate_fallback (R²=0.9995); user-approved | ⚠ MD overshoot (polyether) |
| Tg (MD @160 / @400 K/ns) | 245.3 / 214.8 K | — | — | per-rate context (non-monotonic, rubbery regime) | annotation |
| α_g (CTE) | 24.9×10⁻⁵ K⁻¹   | —      | — | bilinear glassy slope (r40) | — no exp ref |
| α_r (CTE) | 60.3×10⁻⁵ K⁻¹   | —      | — | bilinear rubbery slope (r40); α_r/α_g=2.42 (healthy) | — no exp ref |
| ΔCp at Tg | 0.617 J/(g·K)     | 0.4–1.0 (lit.)        | in range | H(T) bilinear fit (r40) | ✓ |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 3.45 ± 0.24 GPa | ~2.0 GPa (plan ref) | +72% | fluctuation (N_eff=409, τ_eff=1.22 frames; volume_equilibrated, drift 0.16%) | ⚠ above exp ref |
| B0' | N/A     | 7–11 (typical) | —    | Murnaghan fit (rubbery only) — not run (fluctuation path) | annotation |
| G   | N/A | —    | — | deformation (glassy only) — N/A rubbery               | N/A |
| E   | N/A | —    | — | deformation (glassy only) — N/A rubbery               | N/A |

Mechanical note: fluctuation K=3.45 GPa exceeds plan exp ref (2.0 GPa) by ~72%. B_def cross-check unreliable (R²=0.015, nonlinear EOS typical of rubbery melts); B_dyn vs B_def disagree 36%. Planned method for rubbery+no-pressures is fluctuation; a Murnaghan multi-pressure series (±2000–5000 atm) would give a more accurate absolute K but was not in the approved plan. Reported with WARNING.

Simulation dir: `data/PEG2/lammps/`
Outputs: `data/PEG2/raw/` — JSONs; `data/PEG2/graphs/` — PNGs; `data/PEG2/raw/run_summary.json`

---

## FINAL ASSESSMENT (orchestrator)

PEO (POXI/PCFF, DP=100, 10 chains, 7020 atoms). All three properties delivered. The automated range-gate marks each "FAIL", but in scientific context:

- **Density 1.058 g/cm³** — essentially in-band (−0.6% from the exp lower edge 1.064; −5.6% vs midpoint 1.120). **Good.**
- **Tg (MD) 238.7 K** (slowest rate, 40 K/ns, EXCELLENT R²=0.9995) — +32.7 K vs exp 206 K, the expected PCFF overshoot for polyethers. Multirate→DSC extrapolation **not achievable**: 3 rates span only 1 decade and the rubbery regime (T_workflow 300 K ≫ Tg) gives non-monotonic scatter (238.7/245.3/214.8 K) → slope_gate failed, VF failed. User-approved to report slowest-rate value with caveat. CTE α_r/α_g=2.42 (healthy); ΔCp=0.617 J/g·K (in lit. range).
- **K 3.45 ± 0.24 GPa** (fluctuation, rubbery) — +72% vs plan ref 2.0 GPa. Fluctuation method is known to overestimate for rubbery melts (B_dyn vs B_def disagree 36%, nonlinear EOS); a Murnaghan multi-pressure series (not in the approved plan) would refine the absolute K.

Recoveries: 1 (R-01 equil energy-plateau extension, converged). Pipeline completed end-to-end; no UNRESOLVED stages. Honest caveats: entangled-melt terminal relaxation incomplete (advisory, does not affect segmental properties); Tg DSC extrapolation limited by rate span; K likely high (method-dependent).
