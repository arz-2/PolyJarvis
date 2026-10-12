## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=549.69 K · 951 frames analysed (skip=50) · 2026-09-13 10:32

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.571% (p=0.0025) | <1%, p<0.01 | PASS |
| Energy drift | 0.2216% (p=0.2548) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.7357%, angle=0.2101%, dihedral=0.2003%, vdw=0.6135%, coul=0.0%, kspace=0.0% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.1011% | <1% | PASS |
| Energy block-SEM | 0.0755% | <1% | PASS |
| τ_eff density | 0.7% of trajectory | — | OK |
| Independent density samples | 151 | ≥20 | PASS |
| Residual deviatoric stress | 100.9 atm von Mises (max |dev| 65.2 atm, z=3.38, resolved) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 20.0% | <30% | PASS |
| MSID slope (combined) | 1.114 (R²=0.9986) | 1.0 ±20% | OK |
| MSID slope (large-s, n=[61, 180]) | 1.099 (R²=0.9996) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 2e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 207467.1 ps (24% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.271, MSD=2394.11 Å²>>Rg²=1037.833) | — | OK |
| R_ee mean ± std | 76.8 ± 25.07 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0193 ± 0.0066 | <0.10 | PASS |
| Finite size | L=48.8 Å · L/2r_cut=1.743 · L/2Rg=0.774 · L/R_ee=0.635 | ≥1.0 | SIZE_CHAIN_SELF_IMAGE_ADVISORY |
| Density homogeneity CV (signal) | 0.0% (raw 14.8% − Poisson 18.6%; 5³ grid, 28.8 atoms/voxel) | <11% | PASS |

**Warnings:** C(t) partially decayed: 24% decayed at end of trajectory (τ_relax=207467.1 ps vs T_traj=4902.0 ps)