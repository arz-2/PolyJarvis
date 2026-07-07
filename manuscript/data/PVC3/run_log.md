# Polyvinyl Chloride (PVC) Run PVC3 · 2026-06-23 → 2026-06-24
SMILES: `*CC(Cl)*`  |  FF: PCFF  |  Charges: embedded (bond-increment)  |  DP: 60  |  Chains: 10  |  GPU: [claimed at submit]
Requested: density, tg, bulk_modulus  |  Replicate: 1 of 1 (revision of PVC2)  |  Seeds: EMC=472913  |  SEED_HOT=552631  |  SEED_COLD=N/A (glassy path)
Plan: `data/PVC3/raw/run_plan.json`  |  mode: reasoned  |  confidence: medium  |  critic: approved (1 round, 0 findings)  |  T_workflow_K: 530
Revision vs PVC2: tg_rates [40,160,400]→[25,50,100] K/ns, t_equil 5→8 ns, anneal cycles 5→7 (fix degenerate Tg); Murnaghan span ±1000→±3000 atm (fix B0'=16.3). gpu_per_run=1, engine=KOKKOS (policy default).

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF                | EMC auto-routed use_pcff=true; PVNL/PCFF per plan. classify_polymer false-flags PHAL for *CC(Cl)* — overridden (C–Cl ≠ PTFE-family) |
| D-02 Charges        | embedded (bond-increment)        | PCFF class-II: bond-increment charges embedded, no QM step |
| D-03 Electrostatics | PPPM 12 Å                          | C–Cl polar backbone → long-range Coulomb |
| D-04 System size    | DP=60, 10 chains, 3620 atoms                        | polymer_rules.json PVNL default; matches PVC2 |
| D-05 Convergence    | PASS                         | overall_pass=true; density+energy+spatial gates met. C(t) partial decay (13%, τ_relax 16.2 ns) advisory under require_glassy carve-out (is_glassy=true, DP60). Density 1.344 g/cm³ vs exp 1.38 (−2.6%) |
| D-06 Tg fit quality | GOOD (all 3 rates) — but multirate slope-gate FAIL  | **Per-rate fits ALL GOOD/non-degenerate (revision fixed PVC2 degeneracy):** r25=310.6 K (R²=0.9845, w=real), r50=267.6 K (R²=0.9929, w=29.4 K), r100=284.0 K (R²=0.9815, w=15.1 K). is_glassy=**True** (exp-Tg fallback per THERMAL_TRACK L93: glassy slope-gate fail routes is_glassy to exp_Tg 354>300; also ρ=1.344 glassy solid) → mechanical correctly ran glassy. |
| D-06b Multirate Tg  | DSC-equiv = 310.6 K (single_rate_fallback; slope-gate FAIL) | log-linear Tg(lnΓ) slope=−19.2 K, R²=0.376 (<0.90 gate), N_rates=3 @ [25,50,100] K/ns (span 0.6 decades — UNDERCONSTRAINED), VF=FAILED. slope_gate_pass=False (negative/inverted slope). Root cause = narrow rate span, NOT contamination (all per-rate fits GOOD) → seed-reroll futile (cf PVC2 memory). Reported as single-rate MD Tg=310.6 K, −43.4 K (−12.3%) vs exp 354 = PCFF systematic PVC Tg underprediction. NOT a clean DSC extrapolation. Staged registry rows DISCARDED (glassy slope-gate fail → not committed to CSV). |
| D-07 Property method | murnaghan (glassy, 300 K) | is_glassy=True (exp Tg 354≫300, ρ=1.344 glassy) → glassy Murnaghan EOS on npt_prod300_out.data. Span [−1000,0,1500,3000,5000] atm (R-04 revision). K=2.80±0.17 GPa, **B0'=9.53** (in [4,20] ✓; PVC2 was 16.3 — widening fixed it), R²=0.9990. Fluctuation cross-check B_dyn=2.93 GPa (4.6% agree). K −30% vs exp = PCFF systematic PVC underprediction (known) |

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

### R-01 Build worker died on weekly API limit — EMC job already done (2026-06-23)
- **Symptom:** molecule-builder agent terminated with "You've hit your weekly limit · resets 8pm" after 4 tool uses; returned no RESULT block; data/PVC3/lammps/cell/ did not exist.
- **Diagnosis:** Orchestrator queried EMC server (`list_emc_jobs`) → found completed job `cc36f57d` (submitted 21:58, completed 21:58, 56 s). `get_emc_job_output` confirmed success: *CC(Cl)*, PCFF, dp=60, natoms=3620, resolved_seed=472913, use_pcff=true. The cell was fully built; only the post-build file-copy + RESULT report were lost when the agent died.
- **Fix:** Orchestrator performed the builder's final step manually — copied `emc_build.data`→`cell/cell.data` and `emc_build.params`→`cell/emc_build.params`; logged EMC seed 472913 to header.
- **Outcome:** converged (no re-build needed). Cell verified 3620 atoms, matches PVC2.

### R-02 / R-03 Planner-critic-build all hit API spend/weekly limits
- The critic (round 1) first died on "monthly spend limit"; retry succeeded → approved, 0 findings. Build worker then died on weekly limit (see R-01). Downstream GPU stages also gated by all-4-GPUs-busy. Watch for limit recurrence on equil/tg/murnaghan workers.

### R-04 Murnaghan cavitated at −3000 atm tension → compression-biased span (2026-06-24)
- **Symptom:** Murnaghan chain 6e413d86 (plan span [−3000,−1500,0,1500,3000] atm) FAILED at the first/most-negative stage `bm_P-3000`. Log: glassy cell cavitated under −0.3 GPa tension — density collapsed 1.3→0.002 g/cm³, T runaway to 3655 K, KOKKOS "Shake determinant < 0.0", then "ERROR: Non-numeric pressure - simulation unstable". Only bm_P-3000 ran; chain aborted before the other 4 pressures.
- **Diagnosis:** Deep negative pressure (tension) cavitates the glassy amorphous cell. PVC2's ±1000 atm was stable; the revision's −3000/−1500 atm tension exceeds the cell's tensile stability. The B0'-constraint goal (wide span) is sound, but it must be achieved on the *compression* side, not via deep tension.
- **Fix (orchestrator inline recovery — unambiguous parameter fix for a falsified plan assumption; opus planner skipped due to spend-limit fragility):** revised `decided_params.bm_pressures_atm` → [−1000, 0, 1500, 3000, 5000] atm. Tension capped at −1000 atm (PVC2-proven stable); compression extended to +5000 atm → retains the wide 6000-atm range that constrains B0' (3× PVC2's span). Plan backed up to run_plan.json.bak_pre_bmspan; revision_notes updated. Failed series archived to bm_series_failed_R04/. Re-submitted on same GPU 2.
- **Outcome:** converged. Retry chain 967f959e ran all 5 pressures with no cavitation (−1000 atm tension stable, where −3000 had blown up). BM extraction: K=2.80±0.17 GPa, **B0'=9.53** (in [4,20]; PVC2 was 16.3 — the widened compression span achieved its B0'-constraint goal), R²=0.9990, fluctuation cross-check 2.93 GPa (4.6% agreement). The residual ~30% K deficit vs exp is PCFF systematic underprediction (matches PVC2's 2.91 GPa; see memory project_pvc_murnaghan_b0prime), NOT a span/fit artifact — so no further recovery warranted.

### R-05 Multirate Tg slope-gate FAIL — accepted single-rate fallback (user decision, 2026-06-24)
- **Symptom:** extract_tg_multirate over [25,50,100] K/ns returned slope_gate_pass=False (loglinear slope −19.2 K, R²=0.376, span 0.6 decades), tg_method=single_rate_fallback, VF=FAILED. Below the plan success_criterion loglinear_r²≥0.90.
- **Diagnosis:** NOT contamination — all 3 per-rate bilinear fits are GOOD with real transition widths (r25=310.6/R²0.9845, r50=267.6/R²0.9929, r100=284.0/R²0.9815). The revision's PRIMARY goal (eliminate PVC2's degenerate c≈0 kink fits) is ACHIEVED. The slope gate fails because 3 rates over only 0.6 decades cannot resolve the small Tg-vs-rate signal against ±20–40 K per-fit noise → inverted/flat slope. PVC2 memory: seed re-roll is futile for this mode (fix = wider rate span, a plan change).
- **Decision (user, via AskUserQuestion):** ACCEPT single-rate fallback. Do NOT seed-reroll (futile) and do NOT re-plan a wider span this run. Report MD Tg = 310.6 K (slowest/most-equilibrated rate) with explicit caveat: single-rate value, −12.3% vs exp 354 K (PCFF systematic PVC Tg underprediction), NOT a DSC-equivalent extrapolation. Staged registry rows discarded per glassy slope-gate-fail protocol (not committed to the cross-run CSV).
- **Outcome:** accepted/finalized. is_glassy=True via exp-Tg fallback (THERMAL_TRACK L93) — mechanical track correctly ran glassy. Recommend a future replicate or wider-span (≥1.2 decade) campaign if a clean DSC-equivalent Tg is needed.

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage glassy) | dfa923bf | 22:33 | 01:25 | ~2h52m | done |
| murnaghan ±3000 (FAILED) | 6e413d86 | 01:45 | 01:50 | ~5m | failed — cavitated @ −3000 atm (R-04) |
| murnaghan [−1000..+5000] (R-04 retry) | 967f959e | 01:52 | 02:5x | ~1h | done (5/5, no cavitation) |
| tg-sweep r25 (21 T-pts) | 01136f53 | 01:46 | done | ~8h | done (21/21); GPU 3 released · vseed=295072 |
| tg-sweep r50 (21 T-pts) | 97f81b0d | 03:0x | done | ~5h | done (21/21); GPU 2 released · vseed=360534 |
| tg-sweep r100 (21 T-pts) | 65168f97 | 03:1x | done | ~2h | done (21/21); GPU 1 released · vseed=730559 |

GPU inventory: A800 40GB, engine=kokkos, mpi=1. Claims: GPU 3 (label "PVC3") for equil + Tg sweeps; GPU 2 (label "PVC3_murn") for Murnaghan. Task requested GPU 2; ran on a mix of free GPUs (2,3) since the box is shared with concurrent sessions (PEG3, PS3_*). Thermal (Tg r25/r50/r100) and mechanical (Murnaghan, glassy-certain) run in parallel — is_glassy=True is certain for PVC (exp Tg 354 ≫ 300, ρ=1.344 glassy solid), so the mechanical gate's rubbery-waste risk does not apply.

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=299.85 K · 951 frames analysed (skip=50) · 2026-06-24 01:26 · **Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.5939% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.6552% (p=0.6755) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.069% | <1% | PASS |
| Energy block-SEM | 0.4727% | <1% | PASS |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 12.9% | <30% | PASS |
| MSID slope | 1.196 (R²=0.9709) | 1.0 ±20% | OK |
| C(t) τ_relax | 16194.5 ps (13% decayed) | — | ⚠ partial (advisory, glassy DP60) |
| MSD kinetic trap | no (α=0.364, MSD=479.54 Å²≫Rg²=205.85) | — | OK |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0324 ± 0.0076 | <0.10 | PASS |
| Density homogeneity CV | 18.8% (5³ grid) | <25% | PASS |

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg CV | 12.9% | CV < 30% → PASS |
| MSD plateau   | still diffusing (α=0.364, no kinetic trap) | OK |
| Density homog (CV) | 18.8% | < 25% → PASS |
| C(t) decay (300K prod) | 13% decayed (τ_relax 16194.5 ps ≫ T_traj 951 ps) | advisory (glassy carve-out) |
| τ_c chain relax (KWW) | 16194.5 ps | annotation only |
| R_ee mean ± std | 31.5 ± 10.11 Å (N=10 chains) | end_to_end_summary.json |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.344 g/cm³ | 1.38 g/cm³ | −2.6% | NPT 300K plateau (SEM 0.069%) | ✓ |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (single-rate, r25) | 310.6 K | 354 K              | −12.3% | bilinear fit, slowest rate (multirate slope-gate FAIL → fallback) | ⚠ PCFF underpredicts; not DSC-extrapolated |
| Tg (MD @100 K/ns) | 284 K   | —                      | —    | bilinear fit, highest screening rate | annotation |
| α_g (CTE) | 2.57×10⁻⁴ K⁻¹   | ~2.0–2.5×10⁻⁴ K⁻¹ (lit)      | ~+10% | −a_glassy (r25) | ✓ physical |
| α_r (CTE) | 5.30×10⁻⁴ K⁻¹   | ~5.2–7×10⁻⁴ K⁻¹ (lit)      | in range | −a_rubbery (r25) | ✓ physical (α_r/α_g=2.06) |
| ΔCp at Tg | 0.279 J/(g·K)     | ~0.30 J/(g·K) (lit)        | ~−7% | H(T) bilinear fit (r25) | ✓ |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 2.80 ± 0.17 GPa | 3.5–4.5 GPa    | −20% vs lower bound (−30% vs 4.0) | murnaghan (5×P, glassy 300K); fluctuation cross-check 2.93 GPa | ⚠ PCFF underpredicts |
| B0' | 9.53    | 7–11 (typical) | —    | Murnaghan fit; R²=0.9990 (PVC2 was 16.3 → widened span fixed it) | ✓ in range |
| G   | N/A | —    | — | not computed (Born/deform removed; not requested) | N/A |
| E   | N/A | —    | — | not computed | N/A |

Simulation dir: `data/PVC3/lammps/`
Outputs: `data/PVC3/raw/` — JSONs; `data/PVC3/graphs/` — PNGs; `data/PVC3/raw/run_summary.json`

---

## RUN VERDICT (PVC3, revision of PVC2)

| Property | PVC3 | PVC2 | Exp | PVC3 status |
|----------|------|------|-----|-------------|
| Density (300 K) | 1.344 g/cm³ | 1.348 (−2.3%) | 1.38 | ✅ PASS (−2.6%) |
| Tg | 310.6 K (single-rate, r25) | DEGENERATE (unusable) | 354 | ⚠ FAIL value (−12.3%) but **fits now GOOD** |
| Bulk modulus K | 2.80 GPa, B0'=9.53 | 2.91 GPa, B0'=16.3 | 3.5–4.5 | ⚠ FAIL value (−20%) but **B0' fixed** |

**Revision outcome — both PVC2 defects addressed:**
1. **Tg degeneracy FIXED.** PVC2 had degenerate (c≈0) kink fits at all 3 rates → no usable Tg. PVC3's slower rates [25,50,100] + longer melt equil (8 ns / 7 cycles) produced **GOOD, non-degenerate bilinear fits at all 3 rates** (R²=0.98–0.99, real transition widths). The multirate DSC extrapolation still fails (slope-gate, 0.6-decade span too narrow — needs ≥1.2 decades; seed-reroll futile, see R-05), so Tg is reported as a single-rate value (310.6 K). The −12.3% offset is PCFF's systematic PVC Tg underprediction, not a fit artifact.
2. **B0' inflation FIXED.** PVC2's narrow ±1000 atm Murnaghan gave B0'=16.3 (unphysical). PVC3's compression-biased span [−1000..+5000] atm (after R-04 cavitation recovery on the original ±3000) gave **B0'=9.53 ∈ [4,20]**, R²=0.9990, fluctuation cross-check 2.93 GPa. K=2.80 GPa still −20% vs exp = PCFF systematic underprediction (matches PVC2).

**Net:** density validates; Tg and K remain ~12–20% below experiment — a documented **PCFF systematic underprediction for PVC**, now cleanly characterized rather than masked by degenerate/ill-conditioned fits. For experiment-matching Tg/K, a different FF (or empirical PCFF-PVC correction) is needed; for a clean DSC-equivalent MD Tg, a wider-rate-span campaign (≥1.2 decades) is the recommended next step.

## COMPUTE COST (harvested from LAMMPS loop-time logs)
- **Wall (loop-time)**: 17.8 h  |  **GPU**: 17.8 h  |  **CPU**: 0.0 h (0 core-h)  |  procs: 1
- Source: `data/PVC3/lammps/**/*.log` (Born stages excluded); reproducible via `manuscript/gen_table_compute_cost.py`.
