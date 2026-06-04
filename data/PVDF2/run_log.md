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
| D-05 Convergence    | PASS                                   | check_equilibration_comprehensive 2026-06-03: overall_pass=True; T=600K NVT; Rg CV=21.9%; MSID slope=1.419 (⚠ non-Gaussian, soft); P2=0.035; density CV=21.5%. Warnings: MSID extended chains; C(t) τ_relax=22913 ps >> T_traj=951 ps (slow PVDF dynamics). Hard gates all pass. |
| D-06 Tg fit quality | ACCEPTABLE (R²=0.979)                  | bilinear curve_fit; 61 plateau bins 200–610 K; Tg_primary=330 K (in target 310–350 K ✓), Tg_alt=362.7 K; glassy slope=−3.40e-4, rubbery slope=−1.03e-3 g/cm³/K |

**OPLS-AA styles:** pair_style lj/cut/coul/long · dihedral_style multi/harmonic · special_bonds lj/coul 0 0 0.5 · pair_modify mix geometric tail yes

---

## RECOVERIES

None

---

## D-05 CONVERGENCE DETAIL

`check_equilibration_comprehensive` · T=600.0 K · 951 frames · 2026-06-03

**Overall: PASS**

| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0% (NVT — fixed volume) | — | N/A |
| Energy drift | 0.046% (p=0.635) | <1%, p<0.01 | PASS |
| Rg CV (chain–chain) | 21.9% | <30% | PASS |
| MSID slope | 1.419 (R²=0.989) | 1.0 ±20% | ⚠ non-Gaussian (soft) |
| P2 nematic order | 0.035 ± 0.012 | <0.10 | PASS |
| Density homogeneity CV | 21.5% (5³ grid, 29 atoms/voxel) | <25% | PASS |
| MSD kinetic trap | no (α=0.277, MSD=510 Å² > Rg²=361 Å²) | — | OK |
| C(t) τ_relax | 22913 ps (12% decayed) | — | ⚠ slow dynamics |

Notes: Rg_mean=18.5 Å, n_chains=10. MSID slope >1 suggests chain extension — possible effect of short carbon-only backbone definition or actual chain extension at 600K. C(t) slow decay is consistent with known slow PVDF chain dynamics (all-F chain segments). Hard gates all pass.

---

## RESULTS

| Property | Computed | Experimental | Error | Status |
|----------|----------|--------------|-------|--------|
| Tg | 330 K (alt: 362.7 K) | 233 K exp / 310–350 K target MD | +97 K vs exp; in target ✓ | complete |
| Tg R² | 0.979 | — | — | ACCEPTABLE |
| ρ (300K, glassy fit) | 1.528 g/cm³ | 1.78 g/cm³ | −14.2% | ⚠ worse than PVDF1 (−9.2%) |
| ρ (600K, NPT melt) | 1.246 g/cm³ ±0.004 | — | — | equilibrated, T>Tg |
| K (600K, NPT melt) | 0.398 ±0.067 GPa | — | — | B_def=0.290 GPa (27% gap — above 20% threshold) |
| vs PVDF1 (GAFF2_mod) Tg | +53 K improvement (383→330 K) | — | — | OPLS-AA improves Tg ✓ |
| vs PVDF1 density | −14.2% vs −9.2% | — | — | OPLS-AA worsens density ✗ |

**Key finding:** OPLS-AA 2024 (standard LJ params) improves Tg by 53 K vs GAFF2_mod+F-patch but worsens RT density by 5 pp. Root cause: standard OPLS-AA F params (σ=2.94 Å, ε=0.061) are not the Byutner & Smith 2000 Buckingham-6 F–F interaction. Track G1 priority 1 (Byutner2000) is the next step for PVDF density accuracy.

Simulation dir: `/home/arz2/simulations/PVDF2/`
