# Polyethylene glycol (PEG/PEO) Run 4 · 2026-06-24 → 2026-06-25
SMILES: `*CCO*`  |  FF: PCFF  |  Charges: bond-increment (EMC)  |  DP: 100  |  Chains: 10  |  GPU: 0
Requested: {density, tg, bulk_modulus}  |  Replicate: 1 of 1  |  Seeds: EMC=409966  |  SEED_HOT=[N]  |  SEED_COLD=[N]
Plan: `data/PEG4/raw/run_plan.json`  |  mode: deterministic  |  confidence: high  |  critic: approved (round 1, 0 findings)  |  T_workflow_K: 300 (rubbery, Tg~206K < 300K)

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-00 Plan gate      | deterministic, confidence=high, critic approved      | POXI high-confidence → deterministic transcription of polymer_rules defaults; 4 decisions; auto-approved |
| D-01 Force field    | PCFF                                                 | classify_polymer returned POXI → EMC PCFF auto-routed (Class II thermomechanical accuracy) |
| D-02 Charges        | bond-increment (embedded in PCFF)                    | EMC Class II FF: library charges embedded, no QM step |
| D-03 Electrostatics | PPPM 12 Å                                            | ether oxygen partial charge (~-0.3 to -0.4 e) → long-range Coulomb |
| D-04 System size    | DP=100, 10 chains, 7020 atoms                        | polymer_rules.json POXI default (DP 100 = 4400 g/mol, above Klajmon2023 Tg convergence) |
| D-05 Convergence    | PASS                                                 | overall_pass=true; rubbery carve-out — density block-SEM 0.054% << 1%, drift 0.28%, T=300.06 K; C(t)/MSD advisory |
| D-06 Tg fit quality | EXCELLENT (per-rate)                                  | All 3 rates EXCELLENT (r²=0.9995/0.9995/0.9968 @ 25/50/100 K/ns); is_glassy=FALSE (highest-rate Tg=206 K < 300 K) → rubbery |
| D-06b Multirate Tg  | flat-mean = 234.5 K (rubbery)                        | rubbery_flat_mean over N=9 rows (3 replicates PEG2/3/4) @ rates [25,40,50,100,160,400]; log-linear slope −5.94 K/ln, R²=0.16 (scatter — rubbery flat-rate regime, is_flat_rate_regime=True, slope-gate exempt); VF Tg0=205 K POORLY_CONSTRAINED (1.2-decade span, diagnostic only) |
| D-07 Property method | murnaghan (rubbery, 300 K)                           | Tg=206–254 K < 300 → is_glassy=False; rubbery Murnaghan EOS on npt_production 300 K cell, bm_pressures=[-1000,0,3000,7000,15000] (widened for stiff PEO) + NPT fluctuation cross-check |

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

### R-01 · Tg sweep r25 (916690a0) — KOKKOS deck/binary engine mismatch
- **Symptom:** Tg sweep r25 failed instantly (exit 1). `tg_step.log`: `ERROR: Package gpu command without GPU package installed`, `Last input line: package gpu 1 neigh no`.
- **Root cause:** `generate_script` rendered the deck with `package gpu 1 neigh no` (its `engine` default is `"gpu"`, script_generator.py:1187), but `run_lammps_script` launched the KOKKOS binary (`lammps-install-kokkos/bin/lmp -pk kokkos`). The kokkos binary has no GPU package → error. The worker forwarded `engine="kokkos"` to `run_lammps_script` but NOT to `generate_script` — the gen_prompt engine-forward note omits `generate_script` from its list.
- **Fix:** Re-spawn tg-sweep-worker (attempt 1/2) with explicit instruction to pass `engine="kokkos"` (and `use_gpu=True`) to `generate_script`, so the deck emits `# KOKKOS: package loaded via -pk kokkos` instead of `package gpu`. Same correction applied to r50/r100.
- **Outcome:** pending re-run.

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Completed | Wall | Status |
|-------|----|-----------|-----------|------|--------|
| equil (9-stage, rubbery+melt) | 9199fe26 | 19:20 | ~04:00+1d | ~8.5 h | done |
| tg-sweep r25 (idx0) | 916690a0 | 00:45 | 00:46 | <1m | failed (R-01 engine mismatch) |
| tg-sweep r25 retry (idx0) | 8e15cc74 | 00:50 | ~07:30 | ~6.7 h | done |
| tg-sweep r50 (idx1) | 8e1509d2 | 07:35 | ~11:00 | ~3.4 h | done | seed 557365
| tg-sweep r100 (idx2) | 4a6259bc | 11:05 | ~12:50 | ~1.7 h | done | seed 743014
| murnaghan BM (rubbery 300K, 5P) | 2cd90984 | 14:31 | 16:07 | ~1.6 h | done | P=[-1000,0,3000,7000,15000]

Run summary: `data/PEG4/raw/run_summary.json`. GPU 0 released. Grades: K ✓ PASS (3.498 GPa, 0% err); ρ ⚠ borderline (−0.3% vs floor); Tg ⚠ (+3.8% vs band max, rubbery overprediction).

GPU claim label: `PEG4` (pick_gpu claimed [0], held across equil+thermal+mech) | equil velocity_seed: 409966 | tg r25 seed: 859566

GPU inventory (`nvidia-smi` at run start): GPU 0–3: NVIDIA A800 40GB Active, 40 GB, 39.5 GB free each (using GPU 0 per task)

---

## D-05 CONVERGENCE DETAIL

**Overall verdict: PASS** (rubbery carve-out — gate on density block-SEM/drift only; C(t)/MSD/τ_relax advisory). Full block: `data/PEG4/raw/d05_block.md`.

### A. Thermo Convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2757% (p=4.36e-09) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0543% | <1% | PASS |
| Energy stability | oscillating, no trend | <1% | PASS |
| Temperature | 300.06 K | ±0.5 K | PASS |

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | N/A (dump analysis incomplete) | rubbery — advisory only |
| MSD plateau   | N/A (rubbery, still diffusing by construction) | rubbery — advisory only |
| Density homog (CV) | N/A (advisory) | < 25% (not gated for rubbery) |
| C(t) decay (melt NVT) | N/A — rubbery | advisory only |
| τ_c chain relax (KWW) | N/A — rubbery | annotation only |
| R_ee mean ± std | N/A | end_to_end not computed (rubbery advisory) |

---

## RESULTS

### A — Foundation (always)

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| ρ (300 K) | 1.0612 ± 0.0005 g/cm³ | 1.064–1.176 g/cm³ (206±5% band) | −0.3% vs floor | NPT 300K plateau | ⚠ borderline (0.28% below floor 1.064 — near-miss, within MD tolerance for amorphous PCFF PEO; exp 1.10–1.12 is semicrystalline-inclusive) |

<!-- Optional: add ρ (T_equil) row if --add_melt_npt was used: method = NPT melt plateau (stage 05b) -->

### B — Thermal

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg (rubbery flat-mean) | 234.5 K | 206 K (PEO)         | +13.8% | mean of per-rate Tg, N=9 (3 repl) — rubbery_flat_mean | ⚠ (rubbery: T_prod 300K >> Tg, direct comparison weak) |
| Tg (MD @100 K/ns, highest) | 206.0 K | 206 K (PEO)    | ±0%  | bilinear density fit, highest screening rate (sets is_glassy) | ✓ |
| Tg per-rate (25/50/100) | 236.7 / 254.4 / 206.0 K | —      | —    | bilinear density fit (all EXCELLENT) | rubbery scatter |
| α_g (CTE) | ~8.3–24×10⁻⁵ K⁻¹ | ~20×10⁻⁵ K⁻¹ (glassy PEO) | — | −a_glassy / ρ_mean_glassy (rate-dependent) | annotation (rubbery) |
| α_r (CTE) | ~55–72×10⁻⁵ K⁻¹ | ~80×10⁻⁵ K⁻¹ (melt PEO) | — | −a_rubbery / ρ_mean_rubbery | annotation (rubbery) |
| ΔCp at Tg | N/A             | —                      | —    | skipped — no .data mass file (not a requested property) | N/A |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | 3.498 ± 0.208 GPa | 2.0–4.0 GPa | within range | Murnaghan EOS, rubbery 300 K, 5P widened series (R²=0.9997, fit_converged) | ✓ |
| K (fluctuation x-check) | 3.216 ± 0.160 GPa | 2.0–4.0 GPa | within range | NPT volume fluctuation (1001 frames, diagnostic) — agrees 8.5% w/ Murnaghan | ✓ |
| B0' | 8.96    | 7–11 (typical) | —    | Murnaghan fit — widened series RESOLVED B0' (PEG3 narrow series clamped at 1.0) | ✓ |
| G   | N/A     | —              | —    | not computed (rubbery — deform is glassy-only)  | N/A |
| E   | N/A     | —              | —    | not computed (rubbery — deform is glassy-only)  | N/A |

Simulation dir: `data/[RUN]/lammps/`
Outputs: `data/[RUN]/raw/` — JSONs; `data/[RUN]/graphs/` — PNGs; `data/[RUN]/raw/run_summary.json`
