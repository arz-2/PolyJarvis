## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.96 K · 1951 frames analysed (skip=50) · 2026-09-13 01:06

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0416% (p=0.1884) | <1%, p<0.01 | PASS |
| Energy drift | 0.8258% (p=0.0) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.1853%, angle=0.0548%, dihedral=0.0037%, vdw=0.0448%, coul=0.3082%, kspace=0.0916% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0194% | <1% | PASS |
| Energy block-SEM | 0.1103% | <1% | PASS |
| τ_eff density | 0.7% of trajectory | — | OK |
| Independent density samples | 147 | ≥20 | PASS |
| Residual deviatoric stress | 116.7 atm von Mises (max |dev| 70.8 atm, z=3.91, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 18.8% | <30% | PASS |
| MSID slope (combined) | 1.034 (R²=0.9518) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[51, 150]) | 0.641 (R²=0.9875) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 5e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 96009231.3 ps (1% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.28, MSD=267.79 Å²>>Rg²=511.381) | — | ⚠ trapped |
| R_ee mean ± std | 50.76 ± 24.29 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0187 ± 0.0033 | <0.10 | PASS |
| Finite size | L=51.71 Å · L/2r_cut=2.722 · L/2Rg=1.163 · L/R_ee=1.019 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 18.9% − Poisson 26.9%; 8³ grid, 27.4 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 1% decayed at end of trajectory (τ_relax=96009231.3 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state