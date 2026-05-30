# PVDF Run 2 · 2026-05-27 → [END_DATE]
SMILES: `*CC(F)(F)*`  |  FF: OPLS-AA 2024 (EMC)  |  Charges: OPLS-AA fixed  |  DP: 60  |  Chains: 10

---

## DECISIONS

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | OPLS-AA 2024 via EMC                   | GAFF2_mod showed −9.2% density and +150K Tg vs experiment; OPLS-AA has PVDF-specific parametrization (Watkins & Jorgensen 2001, type 962 CF2 / 965 F) |
| D-02 Charges        | OPLS-AA fixed-charge                   | OPLS-AA charges embedded in field (CF2 C: +0.41, F: −0.205, CH2 C: −0.18, H: +0.06); net charge = 0.000 e |
| D-03 Electrostatics | PPPM (lj/cut/coul/long 9.5 Å)         | Highly polar CF2 backbone; geometric mixing; special_bonds lj/coul 0 0 0.5 |
| D-04 System size    | DP=60, 10 chains, 3620 atoms           | Same as PVDF1 for direct comparison; EMC builds at ρ=0.5 g/cm³ starting density |
| D-05 Convergence    | [pending]                              | — |
| D-06 Tg fit quality | [pending]                              | — |

**OPLS-AA styles:** pair_style lj/cut/coul/long · dihedral_style multi/harmonic · special_bonds lj/coul 0 0 0.5 · pair_modify mix geometric tail yes

---

## RECOVERIES

None

---

## D-05 CONVERGENCE DETAIL

[pending — to be filled after equilibration]

---

## RESULTS

| Property | Computed | Experimental | Error | Status |
|----------|----------|--------------|-------|--------|
| Tg       | — K      | 233 K exp / ~310–350 K target MD | — | pending |
| ρ (300K) | — g/cm³  | 1.78 g/cm³ (bulk)   | —    | pending |
| K        | — GPa    | —            | —    | pending |

Simulation dir: `/home/arz2/simulations/PVDF2/`
