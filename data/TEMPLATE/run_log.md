# [POLYMER_NAME] Run [N] · [START_DATE] → [END_DATE]
SMILES: `[SMILES]`  |  FF: [FF]  |  Charges: [CHARGE_METHOD]  |  DP: [DP]  |  Chains: [N_CHAINS]  |  GPU: [IDs used]
Requested: [PROPERTIES]  |  Seeds: EMC=[N or "random"]  |  SEED_HOT=[N]  |  SEED_COLD=[N]
Plan: `[PLAN_PATH = data/[RUN]/raw/run_plan.json]`  |  mode: [deterministic / reasoned]  |  confidence: [high/medium/low]  |  critic: [approved / N rounds]

---

## DECISIONS

<!-- D-00 is the planner/critic gate: the run_plan.json artifact, its mode, and the critic verdict (see Plan: line above). -->
<!-- D-01..D-07 below are the executed decisions; for reasoned plans they are sourced from run_plan.json decided_params. -->
<!-- Fill each row as you reach that stage. Do not leave blank at end of run. -->
<!-- Example values shown in parentheses — replace with actual values. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | [GAFF2 / GAFF2_mod / PCFF / OPLS-AA / TraPPE-UA]  | [classify_polymer returned class X (NAME) → auto-routed / override: REASON] |
| D-02 Charges        | [RESP / AM1-BCC / Gasteiger / embedded in FF]       | [polar backbone / nonpolar, electrostatics negligible / EMC: embedded] |
| D-03 Electrostatics | [PPPM / lj/cut [CUTOFF] Å]                         | [heteroatoms present → PPPM / pure C/H → lj/cut 12 Å, ~3× speedup] |
| D-04 System size    | DP=[N], [N] chains, [N] atoms                       | [polymer_rules.json default / literature: N chains adequate for amorphous Tg / stiff chain: longer DP needed] |
| D-05 Convergence    | [PASS / EXTEND×N / ESCALATE]                        | [overall_pass=true — see D-05 CONVERGENCE DETAIL below / [N] extension(s) needed] |
| D-06 Tg fit quality | [EXCELLENT / ACCEPTABLE / BORDERLINE / ABORT]       | [R²=[X], F-stat tier=[TIER], N=[N] temperature bins; α_g=[X]×10⁻⁵ K⁻¹, α_r=[X]×10⁻⁵ K⁻¹, ΔCp=[X] J/(g·K); if multi-rate: slope=[X] K/ln, Tg@5K/ns=[X] K, VF Tg⁰=[X]±[Y] K] |
| D-07 Property method | [deformation (glassy) / murnaghan (rubbery) / fluctuation (rubbery fallback)] | [Tg=[X] K → is_glassy=[true/false] → method chosen; bm_pressures_atm present=[Y/N]] |

<!-- Example — PS1 completed run:
| D-01 | TraPPE-UA | classify_polymer returned PSTR → EMC TraPPE-UA auto-routed |
| D-02 | embedded in FF | TraPPE-UA: UA charges embedded, no QM step |
| D-03 | lj/cut 12 Å | Pure C/H backbone, no heteroatoms, ~3× faster than PPPM |
| D-04 | DP=50, 10 chains, 5320 atoms | polymer_rules.json default; consistent with Afzal 2021 12k-atom floor |
| D-05 | PASS | density drift 0.4% over last 500 ps; energy plateau confirmed |
| D-06 | ACCEPTABLE | R²=0.93, F-stat GOOD, N=19 bins; range 550→250K in 20K steps |
-->

<!-- Add rows for any non-routine decisions (parameter overrides, custom protocols, etc.) -->

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Format: what failed · diagnosis · fix · outcome — 4 lines max per incident -->

None

<!--
Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts, human review needed)

Example recovery block:

[equilibration-checker]  check_equilibration EXTEND×2 — density still drifting at 2.1% after two 1 ns extensions
           Diagnosis: density_initial=0.60 was too close to experimental RT density; system trapped at over-densified state
           Fix: restarted compress stage with density_initial=0.55; added one extra annealing cycle
           Outcome: converged — density drift 0.7% on third attempt; PASS

[tg-analysis-worker]  extract_thermal failed "fewer than 4 temperature bins populated"
           Diagnosis: T_START=550K was below MD Tg (~580K for this PCFF system); glassy slope missing
           Fix: re-ran sweep with T_START=700K; T_END=200K; T_STEP=10K
           Outcome: converged — R²=0.94, F-stat GOOD, N=25 bins
-->

---

## D-05 CONVERGENCE DETAIL

<!-- Paste result["d05_markdown"] from check_equilibration_comprehensive here. -->
<!-- The tool auto-generates this block — do not fill manually. -->

---

## TIMING

| Worker | Submitted | Completed | Wall time | Throughput |
|--------|-----------|-----------|-----------|------------|
| Cell build | [HH:MM] | [HH:MM] | [Xh Ym] | — |
| Equilibration | [HH:MM] | [HH:MM] | [Xh Ym] | [X ns/day] |
| Tg sweep (thermal track) | [HH:MM] | [HH:MM] | [Xh Ym / — not requested] | [X ns/day] |
| Born / Deform (mechanical track) | [HH:MM] | [HH:MM] | [Xh Ym / — not requested] | — |
| Bulk modulus extraction | [HH:MM] | [HH:MM] | [Xh Ym / — not requested] | — |
| **Total** | | | **[Xh Ym]** | |

<!-- Times are local wall clock. Throughput from LAMMPS log "Performance" line. Stage 1 times from job poll (submitted → completed status). -->

GPU inventory (`nvidia-smi` at run start):
- GPU [ID]: [model], [VRAM] GB, [free] GB free

---

## RESULTS

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| Tg       | [X] K    | [X]–[X] K   | [X]%  | bilinear fit | [✓ / ⚠ outside bounds / N/A — not requested] |
| α_g (CTE)| [X]×10⁻⁵ K⁻¹ | [X]–[X]×10⁻⁵ K⁻¹ | [X]% | −a_glassy / ρ_mean_glassy | [✓ / ⚠ / N/A — Tg not requested] |
| α_r (CTE)| [X]×10⁻⁵ K⁻¹ | [X]–[X]×10⁻⁵ K⁻¹ | [X]% | −a_rubbery / ρ_mean_rubbery | [✓ / ⚠ / N/A — Tg not requested] |
| ΔCp at Tg| [X] J/(g·K) | [X]–[X] J/(g·K) | [X]% | H(T) bilinear fit | [✓ / ⚠ / N/A — skipped (<reason>)] |
| ρ (300 K)| [X] g/cm³| [X]–[X] g/cm³| [X]% | NPT 300K plateau | [✓ / ⚠ / N/A — not requested] |
| ρ (T_equil) | [X] g/cm³ | [X]–[X] g/cm³ | [X]% | NPT melt plateau (05b) | [✓ / ⚠ / N/A (no --add_melt_npt)] |
| K        | [X] GPa  | [X]–[X] GPa  | [X]%  | murnaghan / deformation / fluctuation | [✓ / ⚠ / — no exp. ref. / N/A — not requested] |
| B0'      | [X]      | 7–11 (typical) | —   | Murnaghan fit (rubbery only)  | [annotation / N/A (glassy)] |
| G        | [X] GPa  | [X]–[X] GPa  | [X]%  | deformation (glassy only) | [✓ / ⚠ / N/A] |
| E        | [X] GPa  | [X]–[X] GPa  | [X]%  | deformation (glassy only) | [✓ / ⚠ / N/A] |
| cooling rate | [X] K/ns | ~10⁻⁷ K/ns (exp) | — | — | annotation only |
| expected Tg offset | [80–120 K (screening) / 50–80 K (production)] | — | — | — | from polymer_rules.json + cooling rate |

<!-- cooling_rate_K_per_ns = T_STEP / (N_STEPS_PER_T × timestep_fs × 1e-6)
     e.g. 20 K / (250000 × 2 fs × 1e-6) = 40 K/ns  (TraPPE-UA dt=2 fs)
          20 K / (500000 × 1 fs × 1e-6) = 40 K/ns  (standard dt=1 fs)  →  expected offset 80–120 K (screening)
          20 K / (4000000 × 1 fs × 1e-6) =  5 K/ns  →  expected offset 50–80 K (production) -->

Simulation dir: `[PATH]`
Outputs: `data/[RUN]/outputs/` — CSVs, JSONs, `figures/*.png`, `run_summary.json`
