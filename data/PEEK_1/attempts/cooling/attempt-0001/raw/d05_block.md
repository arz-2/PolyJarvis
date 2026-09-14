## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.79 K · 451 frames analysed (skip=50) · 2026-09-12 02:18

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0327% (p=0.6586) | <1%, p<0.01 | PASS |
| Energy drift | 0.1298% (p=0.1659) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2976%, angle=0.0783%, dihedral=0.1037%, vdw=0.2173%, coul=0.0009%, kspace=0.0062% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0349% | <1% | PASS |
| Energy block-SEM | 0.0345% | <1% | PASS |
| τ_eff density | 0.6% of trajectory | — | OK |
| Independent density samples | 166 | ≥20 | PASS |
| Residual deviatoric stress | 235.6 atm von Mises (max |dev| 146.0 atm, z=2.53, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 22.3% | <30% | PASS |
| MSID slope (combined) | 1.271 (R²=0.9854) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[46, 135]) | 1.001 (R²=0.9989) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 6e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 2024603052.7 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=-0.014, MSD=32.13 Å²>>Rg²=698.707) | — | ⚠ trapped |
| R_ee mean ± std | 64.59 ± 27.3 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0212 ± 0.002 | <0.10 | PASS |
| Finite size | L=41.46 Å · L/2r_cut=2.182 · L/2Rg=0.804 · L/R_ee=0.642 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 15.6% − Poisson 22.5%; 6³ grid, 28.4 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.271 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=2024603052.7 ps vs T_traj=451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state