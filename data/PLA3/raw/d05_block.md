## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.95 K · 951 frames analysed (skip=50) · 2026-06-24 19:44

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0961% (p=0.028) | <1%, p<0.01 | PASS |
| Energy drift | 0.092% (p=0.0526) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0243% | <1% | PASS |
| Energy block-SEM | 0.0165% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 19.8% | <30% | PASS |
| C∞ | 14.963 | lit. varies | INFO |
| MSID slope | 1.21 (R²=0.9971) | 1.0 ±20% | ⚠ non-Gaussian |
| C(t) τ_relax | 5093.1 ps (10% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.262, MSD=296.55 Å²>>Rg²=289.796) | — | OK |
| R_ee mean ± std | 35.41 ± 12.11 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.017 ± 0.0061 | <0.10 | PASS |
| Density homogeneity CV | 23.8% (6³ grid, 20.9 atoms/voxel) | <25% | PASS |

**Warnings:** MSID slope = 1.21 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 10% decayed at end of trajectory (τ_relax=5093.1 ps vs T_traj=951.0 ps)