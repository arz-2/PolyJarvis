# BPA-PC Run 1 · 2026-05-01 → 2026-05-02
SMILES: `*Oc1ccc(C(C)(C)c2ccc(O*)cc2)cc1OC(=O)`  |  FF: PCFF  |  Charges: embedded in FF  |  DP: 40  |  Chains: 10  |  GPU: 0
Seeds: EMC=12345  |  SEED_HOT=111  |  SEED_COLD=222

---

## DECISIONS

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 | PCFF | classify_polymer returned PCBN → EMC PCFF auto-routed |
| D-02 | embedded in FF | EMC: embedded bond-increment charges |
| D-03 | pppm 12 Å | carbonate + bisphenol partial charges → long-range Coulomb |
| D-04 | DP=40, 10 chains, 13120 atoms | polymer_rules.json default |
| D-05 | PASS | density drift 0.5% over last 500 ps; energy plateau confirmed |
| D-06 | ACCEPTABLE | R²=0.95, F-stat GOOD, N=21 bins |

---

## RECOVERIES

<!--
Example recovery block (instructional — must NOT be counted by the parser):

[Stage 9]  some_tool failed for an example reason
           Diagnosis: this is only an example inside an HTML comment
           Fix: nothing
           Outcome: escalated
-->

None

---

## RESULTS

| Property | Computed | Experimental | Error | Status |
|----------|----------|--------------|-------|--------|
| Tg | 528 K | 422 K | 25% | ⚠ outside bounds |
| ρ | 1.19 g/cm³ | 1.20 g/cm³ | 0.8% | ✓ |
| K | 4.1 GPa | 3.5–4.0 GPa | — | ⚠ |
| cooling rate | 40 K/ns | ~10⁻⁷ K/ns (exp) | — | annotation only |

Simulation dir: `/remote/PC1`
