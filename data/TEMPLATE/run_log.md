# [POLYMER_NAME] Run [N] · [START_DATE] → [END_DATE]
SMILES: `[SMILES]`  |  FF: [FF]  |  Charges: [CHARGE_METHOD]  |  DP: [DP]  |  Chains: [N_CHAINS]  |  GPU: [IDs used]
Seeds: EMC=[N or "random"]  |  SEED_HOT=[N]  |  SEED_COLD=[N]

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
| D-05 Convergence    | [PASS / EXTEND×N / ESCALATE]                        | [overall_pass=true — see D-05 CONVERGENCE DETAIL below / [N] extension(s) needed] |
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
Outcome options: converged / failed again / escalated / UNRESOLVED (stop after 2 attempts, human review needed)

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

## D-05 CONVERGENCE DETAIL

<!-- Paste result["d05_markdown"] from check_equilibration_comprehensive here. -->
<!-- The tool auto-generates this block — do not fill manually. -->

---

## TIMING

| Stage | Submitted | Completed | Wall time | Throughput |
|-------|-----------|-----------|-----------|------------|
| 1 — Cell build | [HH:MM] | [HH:MM] | [Xh Ym] | — |
| 2 — Equilibration | [HH:MM] | [HH:MM] | [Xh Ym] | [X ns/day] |
| 3 — Tg sweep | [HH:MM] | [HH:MM] | [Xh Ym] | [X ns/day] |
| **Total** | | | **[Xh Ym]** | |

<!-- Times are local wall clock. Throughput from LAMMPS log "Performance" line. Stage 1 times from job poll (submitted → completed status). -->

GPU inventory (`nvidia-smi` at run start):
- GPU [ID]: [model], [VRAM] GB, [free] GB free

---

## RESULTS

| Property | Computed | Experimental | Error | Status |
|----------|----------|--------------|-------|--------|
| Tg       | [X] K    | [X]–[X] K   | [X]%  | [✓ / ⚠ outside bounds] |
| ρ        | [X] g/cm³| [X]–[X] g/cm³| [X]% | [✓ / ⚠] |
| K        | [X] GPa  | [X]–[X] GPa  | [X]%  | [✓ / ⚠ / — no exp. ref.] |
| cooling rate | [X] K/ns | ~10⁻⁷ K/ns (exp) | — | annotation only |
| expected Tg offset | [80–120 K (screening) / 50–80 K (production)] | — | — | from polymer_rules.json + cooling rate |

<!-- cooling_rate_K_per_ns = T_STEP / (N_STEPS_PER_T × timestep_fs × 1e-6)
     e.g. 20 K / (500000 × 1 fs × 1e-6) = 40 K/ns  →  expected offset 80–120 K (screening)
          20 K / (4000000 × 1 fs × 1e-6) =  5 K/ns  →  expected offset 50–80 K (production) -->

Simulation dir: `[REMOTE_PATH]`
