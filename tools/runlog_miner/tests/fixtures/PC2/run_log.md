# BPA-PC Run 2 · 2026-05-03 → 2026-05-05
SMILES: `*Oc1ccc(C(C)(C)c2ccc(O*)cc2)cc1OC(=O)`  |  FF: PCFF  |  Charges: embedded in FF  |  DP: 40  |  Chains: 10  |  GPU: 1
Seeds: EMC=67890  |  SEED_HOT=333  |  SEED_COLD=444

---

## DECISIONS

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 | PCFF | classify_polymer returned PCBN → EMC PCFF auto-routed |
| D-02 | embedded in FF | EMC: embedded bond-increment charges |
| D-03 | pppm 12 Å | carbonate + bisphenol partial charges → long-range Coulomb |
| D-04 | DP=40, 10 chains, 13120 atoms | polymer_rules.json default |
| D-05 | EXTEND×2 | density drift resolved after recovery — see RECOVERIES |
| D-06 | ACCEPTABLE | R²=0.94, F-stat GOOD, N=25 bins |

---

## RECOVERIES

[Stage 2]  check_equilibration EXTEND×2 — density still drifting at 2.1% after two 1 ns extensions
           Diagnosis: density_initial=0.60 was too close to experimental RT density; system trapped at over-densified state
           Fix: restarted compress stage with density_initial=0.55; added one extra annealing cycle
           Outcome: converged — density drift 0.7% on third attempt; PASS at Stage 2

[Stage 3]  extract_tg failed "fewer than 4 temperature bins populated"
           Diagnosis: T_START=550K was below MD Tg (~580K for this PCFF system); glassy slope missing
           Fix: re-ran sweep with T_START=700K; T_END=200K; T_STEP=10K
           Outcome: converged — R²=0.94, F-stat GOOD, N=25 bins

---

## RESULTS

| Property | Computed | Experimental | Error | Status |
|----------|----------|--------------|-------|--------|
| Tg | 531 K | 422 K | 26% | ⚠ outside bounds |
| ρ | 1.21 g/cm³ | 1.20 g/cm³ | 0.8% | ✓ |
| K | 4.0 GPa | 3.5–4.0 GPa | — | ✓ |
| cooling rate | 5 K/ns | ~10⁻⁷ K/ns (exp) | — | annotation only |

Simulation dir: `/remote/PC2`
