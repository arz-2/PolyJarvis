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
| D-05 Convergence    | PASS                       | check_equilibration_comprehensive 2026-06-03: overall_pass=True; T=300K NVT; Rg CV=9.2%; MSID slope=1.035 (Gaussian); P2=0.016; density CV=19.0%. Soft warnings: C(t) not decayed (kinetically trapped — expected below Tg); MSD kinetic trap (expected below Tg). Density 1.1677 g/cm³ at fixed NVT volume, −2.7% vs exp. |
| D-06 Tg fit quality | GOOD (R²=0.9905)           | bilinear curve_fit; 78 plateau bins 200–715 K; Tg_primary=520 K (in target 500–540 K ✓), Tg_alt=477.5 K; glassy slope=−3.19e-4, rubbery slope=−4.41e-4 g/cm³/K |

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
| Tg       | 520 K (alt: 477.5 K) | 422 K | +98 K (+23%) | ✓ in target 500–540 K (40 K/ns rate) |
| density  | 1.1677 g/cm³ (NVT 300K) | 1.20 g/cm³ | −2.7% | ✓ within 5% |
| K        | — GPa | — | — | ⚠ no valid equilibrated NPT at 300K; 05_npt_cool (cooling ramp, 4% drift) and 04_npt_pppm (compression, 24.7% drift) both non-equilibrium — needs dedicated NPT run |
| cooling rate | 40 K/ns | ~1e-7 K/ns (exp) | — | annotation only |
| Tg R²    | 0.9905 | — | — | GOOD; 78 plateau bins |

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=300.03 K · 951 frames · 2026-06-03

**Overall: PASS**

| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0% (NVT — fixed volume) | — | N/A |
| Energy drift | 0.066% (p=0.95) | <1%, p<0.01 | PASS |
| Rg CV (chain–chain) | 9.2% | <30% | PASS |
| MSID slope | 1.035 (R²=0.982) | 1.0 ±20% | PASS |
| P2 nematic order | 0.016 ± 0.004 | <0.10 | PASS |
| Density homogeneity CV | 19.0% (5³ grid) | <25% | PASS |
| MSD kinetic trap | yes (α=0.09, MSD=135 Å² < Rg²=394 Å²) | — | ⚠ expected below Tg |
| C(t) τ_relax | ~2×10⁹ ps (0% decayed) | — | ⚠ expected below Tg |

Notes: Rg_mean=19.8 Å, n_chains=5 (≈10 original, half at backbone types). MSID is Gaussian. Kinetic trap and C(t) non-decay are both expected physical behavior at 300K < Tg(520K).

## SIMULATION STATE
| Stage | run_id / chain | status | last update | output_path |
|-------|---------------|--------|-------------|-------------|
| Equilibration | chain in `/home/arz2/simulations/BPAPC1/` | done | 2026-05-29 | `/home/arz2/simulations/BPAPC1/` |
| Tg sweep | tg_sweep3 (GPU 1,2, MPI=2) | done | 2026-06-01 | `/home/arz2/simulations/BPAPC1/tg_sweep3/` |
| Analysis | runs a62ca7f3 (equil), e9b576be (Tg) | done | 2026-06-03 | `/home/arz2/simulations/BPAPC1/analysis/` |

Simulation dir: `/home/arz2/simulations/BPAPC1`
