## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.15 K · 1951 frames analysed (skip=50) · 2026-06-28 11:14

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1925% (p=0.0636) | <1%, p<0.01 | PASS |
| Energy drift | 0.4559% (p=0.4705) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.1172% | <1% | PASS |
| Energy block-SEM | 0.3054% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 16.3% | <30% | PASS |
| MSID slope | 1.227 (R²=0.9994) | 1.0 ±20% | ⚠ non-Gaussian |
| C(t) τ_relax | 902578.5 ps (8% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.245, MSD=707.97 Å²>>Rg²=241.585) | — | OK |
| R_ee mean ± std | 34.24 ± 12.67 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0193 ± 0.007 | <0.10 | PASS |
| Density homogeneity CV | 20.9% (5³ grid, 32.2 atoms/voxel) | <25% | PASS |

**Warnings:** MSID slope = 1.227 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 8% decayed at end of trajectory (τ_relax=902578.5 ps vs T_traj=1951.0 ps)