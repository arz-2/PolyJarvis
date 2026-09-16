## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=700.1 K · 1951 frames analysed (skip=50) · 2026-09-15 13:51

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 1.3526% (p=0.0002) | <1%, p<0.01 | PASS |
| Energy drift | 0.3095% (p=0.0409) | <1%, p<0.01 | PASS |
| Energy component drift | bond=0.0772%, angle=0.5%, dihedral=0.2842%, vdw=2.25%, coul=0.161%, kspace=0.0202% | <1%, p<0.01 each | PASS |
| Density block-SEM | 0.5568% | <1% | PASS |
| Energy block-SEM | 0.1027% | <1% | PASS |
| τ_eff density | 3.7% of trajectory | — | OK |
| Independent density samples | 27 | ≥20 | PASS |
| Residual deviatoric stress | 49.2 atm von Mises (max |dev| 32.6 atm, z=0.91, not resolved (z<2)) | — | INFO |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 12.4% | <30% | PASS |
| MSID slope (combined) | 1.524 (R²=0.9975) | 1.0 ±20% | ⚠ non-Gaussian |
| MSID slope (large-s, n=[18, 51]) | 1.363 (R²=0.9995) | 1.0 ±20% | ⚠ non-Gaussian (large-s) |
| Torsion JS-divergence (last block-pair) | 9e-05 | ≤0.05 | OK (stable) |
| C(t) τ_relax | 3639.6 ps (65% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.258, MSD=1692.44 Å²>>Rg²=327.637) | — | OK |
| R_ee mean ± std | 44.32 ± 15.94 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0361 ± 0.0104 | <0.10 | PASS |
| Finite size | L=39.01 Å · L/2r_cut=n/a · L/2Rg=1.096 · L/R_ee=0.88 | ≥1.0 | PASS |
| Density homogeneity CV (signal, split_half) | 0.0% (structure shared by both halves of the hold, half-map r=-0.007; 5³ grid, 24.2 atoms/voxel) | <11% | PASS |

**Warnings:** MSID slope = 1.524 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 65% decayed at end of trajectory (τ_relax=3639.6 ps vs T_traj=4951.0 ps)