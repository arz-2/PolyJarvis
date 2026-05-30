# BPA-PC Run 1 | 2026-05-29
SMILES: `*OC(=O)Oc1ccc(C(C)(C)c2ccc(*)cc2)cc1`  |  FF: PCFF (EMC)  |  Charges: embedded  |  DP: 20  |  Chains: ~10 (ntotal=3000)

C5 validation run — PCBN class, target MD Tg 500–540 K vs experimental 422 K.

---

## DECISIONS

| ID | Choice | Rationale |
|----|--------|-----------|
| D-01 Force field    | PCFF (EMC, auto)           | classify_polymer → PCBN; lammps_flags use_pcff=True |
| D-02 Charges        | embedded in PCFF           | no separate charge step for EMC path |
| D-03 Electrostatics | pppm                       | carbonate + aromatic groups; mandatory |
| D-04 System size    | DP=20, ntotal=3000, ~10 chains | standard C5 screening size |
| D-05 Convergence    | PASS                       | density = 1.1677 g/cm³ constant across 1M steps; exp = 1.20 g/cm³ (−2.7%) |
| D-06 Tg fit quality | [PENDING]                  | — |

---

## RECOVERIES

[Stage 2]  nvt_softheat crashed: "Pair style requires a KSpace style"
           Diagnosis: emc_build.params contained `pair_style lj/class2/coul/long` which
                      overrode the .in template's `coul/cut`, forcing coul/long without kspace.
           Fix: stripped pair_style/bond_style/etc. from emc_build.params (coefficients only);
                added permanent fix to smiles_to_emc.py run_emc_build() to auto-strip on all future builds.
           Outcome: chain resumed from stage 02 with corrected params file.

---

## RESULTS

| Property | Computed | Experimental | Error | Status |
|----------|----------|--------------|-------|--------|
| Tg       | [PENDING] | 422 K        | —     | — |
| density  | 1.1677 g/cm3 | 1.20 g/cm3 | −2.7% | ✓ within 5% |
| K        | —         | —            | —     | — |
| cooling rate | [PENDING] | ~1e-7 K/ns | — | annotation only |

Simulation dir: `/home/arz2/simulations/BPAPC1`
