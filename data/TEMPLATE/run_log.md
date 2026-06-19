# [POLYMER_NAME] Run [N] · [START_DATE] → [END_DATE]
SMILES: `[SMILES]`  |  FF: [FF]  |  Charges: [CHARGE_METHOD]  |  DP: [DP]  |  Chains: [N_CHAINS]  |  GPU: [IDs used]
Requested: [PROPERTIES]  |  Replicate: [1 of 1 / N of 5]  |  Seeds: EMC=[N or "random"]  |  SEED_HOT=[N]  |  SEED_COLD=[N]
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
| D-06 Tg fit quality | [EXCELLENT / ACCEPTABLE / BORDERLINE / ABORT / N/A]  | [R²=[X], F-stat=[TIER], N=[N] bins; α_g=[X]×10⁻⁵ K⁻¹, α_r=[X]×10⁻⁵ K⁻¹, ΔCp=[X] J/(g·K) / N/A — tg not requested] |
| D-07 Property method | [born (glassy) / deform fallback (glassy) / murnaghan (rubbery) / fluctuation (rubbery fallback) / N/A] | [Tg=[X] K → is_glassy=[true/false]; bm_pressures_atm=[Y/N] / N/A — bulk_modulus not requested] |

<!-- Add rows for non-routine decisions (parameter overrides, custom protocols, etc.) -->

---

## RECOVERIES

<!-- One block per incident. Write "None" if the run completed without errors. -->
<!-- Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts) -->

None

---

## SIMULATION STATE

<!-- Written before each Monitor call; updated to done/failed after Monitor returns. Used for session restart. -->

| Stage | ID | Submitted | Status |
|-------|----|-----------|--------|
| [equil / tg-sweep / born / deform / murnaghan] | [chain_id / run_id] | [HH:MM] | [monitoring / done / failed] |

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

## TIMING

| Worker | Submitted | Completed | Wall time | Throughput |
|--------|-----------|-----------|-----------|------------|
| Cell build | [HH:MM] | [HH:MM] | [Xh Ym] | — |
| Equilibration | [HH:MM] | [HH:MM] | [Xh Ym] | [X ns/day] |
| Tg sweep | [HH:MM] | [HH:MM] | [Xh Ym / — not requested] | [X ns/day] |
| Born / Deform / Murnaghan | [HH:MM] | [HH:MM] | [Xh Ym / — not requested] | — |
| **Total** | | | **[Xh Ym]** | |

GPU inventory (`nvidia-smi` at run start):
- GPU [ID]: [model], [VRAM] GB, [free] GB free

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
| Tg        | [X] K           | [X]–[X] K              | [X]% | bilinear fit              | [✓ / ⚠] |
| α_g (CTE) | [X]×10⁻⁵ K⁻¹   | [X]–[X]×10⁻⁵ K⁻¹      | [X]% | −a_glassy / ρ_mean_glassy | [✓ / ⚠] |
| α_r (CTE) | [X]×10⁻⁵ K⁻¹   | [X]–[X]×10⁻⁵ K⁻¹      | [X]% | −a_rubbery / ρ_mean_rubbery | [✓ / ⚠] |
| ΔCp at Tg | [X] J/(g·K)     | [X]–[X] J/(g·K)        | [X]% | H(T) bilinear fit         | [✓ / ⚠ / N/A] |
| cooling rate | [X] K/ns    | ~10⁻⁷ K/ns (exp)       | —    | —                         | annotation |
| expected Tg offset | [80–120 K (screening) / 50–80 K (production)] | — | — | — | annotation |

### C — Mechanical

| Property | Computed | Experimental | Error | Method | Status |
|----------|----------|--------------|-------|--------|--------|
| K   | [X ± Y_sem] GPa | [X]–[X] GPa    | [X]% | born (N_eff=[N], τ_ac≈[X] ps) / deform / murnaghan / fluctuation (N_eff=[N], τ_eff=[X]%) | [✓ / ⚠ / — no exp. ref.] |
| B0' | [X]     | 7–11 (typical) | —    | Murnaghan fit (rubbery only)            | annotation |
| G   | [X] GPa | [X]–[X] GPa    | [X]% | deformation (glassy only)               | [✓ / ⚠ / N/A] |
| E   | [X] GPa | [X]–[X] GPa    | [X]% | deformation (glassy only)               | [✓ / ⚠ / N/A] |

### D — Chain Structure

| Metric | Value | Status |
|--------|-------|--------|
| Rg mean ± std     | [X ± Y] Å | [sourced from D-05] |
| MSD plateau       | [plateau / still diffusing] | [PASS / FAIL] |
| Density homog (CV)| [X]% | [PASS / FAIL] |
| C(t) decay (melt NVT) | [X%] / N/A — rubbery | [PASS / FAIL] |
| τ_c chain relax (KWW) | [X] ps / N/A — rubbery | annotation only |
| R_ee mean ± std   | [X ± Y] Å (N=[N] chains) | [sourced from D-05] |

Simulation dir: `[PATH]`
Outputs: `data/[RUN]/outputs/` — CSVs, JSONs, `figures/*.png`, `run_summary.json`
