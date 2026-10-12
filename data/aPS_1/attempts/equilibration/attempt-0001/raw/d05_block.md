## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=572.9 K · 5951 frames analysed (skip=50) · 2026-09-15 11:08

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.3397% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.0504% (p=0.2835) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1194%, angle=0.2757%, dihedral=1.5985%, vdw=0.7715%, coul=0.0251%, kspace=0.0341% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0982% | <1% | PASS |
| Energy block-SEM | 0.0287% | <1% | PASS |
| τ_eff density | 0.7% of trajectory | — | OK |
| Independent density samples | 146 | ≥20 | PASS |
| Residual deviatoric stress | 17.7 atm von Mises (max |dev| 11.4 atm, z=0.67, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 12.0% | <30% | PASS |
| MSID slope (combined) | 1.323 (R²=0.9856) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[19, 52]) | 0.98 (R²=0.9958) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 0.00021 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 31235.6 ps (20% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.203, MSD=593.22 Å²>>Rg²=228.925) | — | OK |
| R_ee mean ± std | 35.73 ± 10.83 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.029 ± 0.0093 | <0.10 | PASS |
| Finite size | L=45.74 Å · L/2r_cut=2.407 · L/2Rg=1.524 · L/R_ee=1.28 | ≥1.0 | PASS |
| Density homogeneity CV (signal, split_half) | 4.4% (structure shared by both halves of the hold, half-map r=0.218; 7³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.323 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 20% decayed at end of trajectory (τ_relax=31235.6 ps vs T_traj=4951.0 ps)