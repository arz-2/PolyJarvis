## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=570.86 K · 3951 frames analysed (skip=50) · 2026-09-15 00:36

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.4974% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.3003% (p=0.0255) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2628%, angle=0.0553%, dihedral=0.0891%, vdw=6.0994%, coul=0.0688%, kspace=0.0094% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0807% | <1% | PASS |
| Energy block-SEM | 0.0688% | <1% | PASS |
| τ_eff density | 0.4% of trajectory | — | OK |
| Independent density samples | 271 | ≥20 | PASS |
| Residual deviatoric stress | 50.6 atm von Mises (max |dev| 29.2 atm, z=1.45, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 23.4% | <30% | PASS |
| MSID slope (combined) | 1.258 (R²=0.9804) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[29, 82]) | 0.936 (R²=0.9998) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 7e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 22964.3 ps (28% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.295, MSD=1478.76 Å²>>Rg²=433.344) | — | OK |
| R_ee mean ± std | 52.51 ± 22.62 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0261 ± 0.0091 | <0.10 | PASS |
| Finite size | L=41.63 Å · L/2r_cut=2.191 · L/2Rg=1.032 · L/R_ee=0.793 | ≥1.0 | PASS |
| Density homogeneity CV (signal, split_half) | 0.3% (structure shared by both halves of the hold, half-map r=0.032; 6³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.258 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 28% decayed at end of trajectory (τ_relax=22964.3 ps vs T_traj=4951.0 ps)