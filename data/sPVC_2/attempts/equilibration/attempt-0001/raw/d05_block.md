## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=571.05 K · 3951 frames analysed (skip=50) · 2026-09-10 22:41

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0603% (p=0.4599) | <1%, p<0.01 | PASS |
| Energy drift | 0.1345% (p=0.3302) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.2673%, angle=0.1664%, dihedral=0.0834%, vdw=0.236%, coul=0.0496%, kspace=0.0301% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.0744% | <1% | PASS |
| Energy block-SEM | 0.0654% | <1% | PASS |
| τ_eff density | 0.4% of trajectory | — | OK |
| Independent density samples | 265 | ≥20 | PASS |
| Residual deviatoric stress | 16.9 atm von Mises (max |dev| 11.3 atm, z=0.56, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 18.0% | <30% | PASS |
| MSID slope (combined) | 1.277 (R²=0.9828) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[29, 82]) | 0.962 (R²=0.9993) | 1.0 ±20% | OK |
| Torsion JS-divergence (last block-pair) | 6e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 9174.3 ps (42% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.294, MSD=1017.18 Å²>>Rg²=429.38) | — | OK |
| R_ee mean ± std | 49.38 ± 20.37 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.022 ± 0.0081 | <0.10 | PASS |
| Finite size | L=41.8 Å · L/2r_cut=2.2 · L/2Rg=1.03 · L/R_ee=0.846 | ≥1.0 | PASS |
| Density homogeneity CV (signal) | 0.0% (raw 22.0% − Poisson 32.3%; 6³ grid, 22.9 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.277 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 42% decayed at end of trajectory (τ_relax=9174.3 ps vs T_traj=4951.0 ps)