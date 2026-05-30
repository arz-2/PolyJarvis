# [POLYMER_NAME] Run [N] · [START_DATE] → [END_DATE]
SMILES: `[SMILES]`  |  FF: [FF]  |  Charges: [CHARGE_METHOD]  |  DP: [DP]  |  Chains: [N_CHAINS]

---

## DECISIONS

<!-- Fill each row as you reach that stage. Do not leave blank at end of run. -->
<!-- Example values shown in parentheses — replace with actual values. -->

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | [GAFF2 / GAFF2_mod / PCFF / OPLS-AA / TraPPE-UA]  | [classify_polymer returned class X (NAME) → auto-routed / override: REASON] |
| D-02 Charges        | [RESP / AM1-BCC / Gasteiger / embedded in FF]       | [polar backbone / nonpolar, electrostatics negligible / EMC: embedded] |
| D-03 Electrostatics | [PPPM / lj/cut [CUTOFF] Å]                         | [heteroatoms present → PPPM / pure C/H → lj/cut 12 Å, ~3× speedup] |
| D-04 System size    | DP=[N], [N] chains, [N] atoms                       | [polymer_rules.json default / literature: N chains adequate for amorphous Tg / stiff chain: longer DP needed] |
| D-05 Convergence    | [PASS / EXTEND×N / ESCALATE]                        | [density drift [X]% over last 500 ps, energy stable / [N] ns extension(s) needed] |
| D-06 Tg fit quality | [EXCELLENT / ACCEPTABLE / BORDERLINE / ABORT]       | [R²=[X], F-stat tier=[TIER], N=[N] temperature bins] |

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
Example recovery block:

[Stage 2]  check_equilibration EXTEND×2 — density still drifting at 2.1% after two 1 ns extensions
           Diagnosis: density_initial=0.60 was too close to experimental RT density; system trapped at over-densified state
           Fix: restarted compress stage with density_initial=0.55; added one extra annealing cycle
           Outcome: converged — density drift 0.7% on third attempt; PASS at Stage 2

[Stage 3]  extract_tg failed "fewer than 4 temperature bins populated"
           Diagnosis: T_START=550K was below MD Tg (~580K for this PCFF system); glassy slope missing
           Fix: re-ran sweep with T_START=700K; T_END=200K; T_STEP=10K
           Outcome: converged — R²=0.94, F-stat GOOD, N=25 bins
-->

---

## RESULTS

| Property | Computed | Experimental | Error | Status |
|----------|----------|--------------|-------|--------|
| Tg       | [X] K    | [X]–[X] K   | [X]%  | [✓ / ⚠ outside bounds] |
| ρ        | [X] g/cm³| [X]–[X] g/cm³| [X]% | [✓ / ⚠] |
| K        | [X] GPa  | [X]–[X] GPa  | [X]%  | [✓ / ⚠ / — no exp. ref.] |
| cooling rate | [X] K/ns | ~10⁻⁷ K/ns (exp) | — | annotation only |

<!-- cooling_rate_K_per_ns = (T_start - T_end) / (n_stages × n_steps × timestep_fs × 1e-6) -->

Simulation dir: `[REMOTE_PATH]`
