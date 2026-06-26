# [POLYMER_NAME] Run [N] · [START_DATE] → [END_DATE]
SMILES: `[SMILES]`  |  FF: [FF]  |  Charges: [CHARGE_METHOD]  |  DP: [DP]  |  Chains: [N_CHAINS]  |  GPU: [IDs used]
Requested: [PROPERTIES]  |  Replicate: [1 of 1 / N of 5]  |  Seeds: EMC=[N]  |  SEED_HOT=[N]  |  SEED_COLD=[N]
Plan: `[PLAN_PATH = data/[RUN]/raw/run_plan.json]`  |  mode: [deterministic / reasoned]  |  confidence: [high/medium/low]  |  critic: [approved / N rounds]  |  T_workflow_K: [N]

---

## DECISIONS

<!-- D-00 = planner/critic gate (see Plan: line). D-01–D-07 = executed decisions from run_plan.json. Fill each row as reached. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | [GAFF2 / PCFF / OPLS-AA / TraPPE-UA]                | [classify_polymer returned class X → auto-routed / override: REASON] |
| D-02 Charges        | [RESP / AM1-BCC / Gasteiger / embedded in FF]        | [polar backbone / nonpolar / EMC: embedded] |
| D-03 Electrostatics | [PPPM / lj/cut [CUTOFF] Å]                          | [heteroatoms → PPPM / pure C/H → lj/cut 12 Å] |
| D-04 System size    | DP=[N], [N] chains, [N] atoms                        | [polymer_rules.json default / literature N chains / stiff chain] |
| D-05 Convergence    | [PASS / EXTEND×N / ESCALATE]                         | [overall_pass=true / [N] extension(s) needed] |
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

None

---

## SIMULATION STATE

<!-- Written before launching each BACKGROUND-WAIT waiter; updated to done/failed on the completion
     wakeup. Used for session restart. BgTask = the run_in_background Bash task id of the live waiter
     (— once it has returned), so a restarting session can tell whether a waiter is still in flight. -->

| Stage | ID | BgTask | Submitted | Completed | Wall | Status |
|-------|----|--------|-----------|-----------|------|--------|
| [equil / tg-sweep / deform / murnaghan] | [chain_id / run_id] | [bg task id / —] | [HH:MM] | [HH:MM / —] | [Xh Ym / —] | [monitoring / done / failed] |

GPU inventory (`nvidia-smi` at run start): GPU [ID]: [model], [VRAM] GB, [free] GB free

---

## D-05 CONVERGENCE DETAIL

<!-- Paste result["d05_markdown"] from check_equilibration_comprehensive here. -->

### Chain Structure Summary

| Metric | Value | Gate |
|--------|-------|------|
| Rg mean ± std | [X ± Y] Å | CV < 30% → [PASS / FAIL] |
| MSD plateau   | [plateau / still diffusing] | [PASS / FAIL] |
| Density homog (CV) | [X]% | < 25% → [PASS / FAIL] |
| C(t) decay (melt NVT) | [X%] at threshold [Y] / N/A — rubbery | [PASS / FAIL] |
| τ_c chain relax (KWW) | [X] ps / N/A — rubbery | annotation only |
| R_ee mean ± std | [X ± Y] Å (N=[N] chains) | end_to_end_summary.json |

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
