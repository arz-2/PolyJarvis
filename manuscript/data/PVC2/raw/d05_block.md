## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.97 K · 951 frames analysed (skip=50) · 2026-06-22 21:44

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.5811% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.2967% (p=0.848) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0766% | <1% | PASS |
| Energy block-SEM | 0.716% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 23.1% | <30% | PASS |
| MSID slope | 1.294 (R²=0.9831) | 1.0 ±20% | ⚠ non-Gaussian |
| C(t) τ_relax | 17552.8 ps (12% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.294, MSD=702.75 Å²>>Rg²=269.196) | — | OK |
| R_ee mean ± std | 38.67 ± 15.6 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0509 ± 0.0103 | <0.10 | PASS |
| Density homogeneity CV | 18.7% (5³ grid, 29.0 atoms/voxel) | <25% | PASS |

**Warnings:** MSID slope = 1.294 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 12% decayed at end of trajectory (τ_relax=17552.8 ps vs T_traj=951.0 ps)