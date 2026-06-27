## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.95 K · 1951 frames analysed (skip=50) · 2026-06-22 20:59

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.2128% (p=0.0001) | <1%, p<0.01 | PASS |
| Energy drift | 0.1412% (p=0.1559) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.039% | <1% | PASS |
| Energy block-SEM | 0.0504% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 11.6% | <30% | PASS |
| C∞ | 14.303 | lit. varies | INFO |
| MSID slope | 1.447 (R²=0.995) | 1.0 ±20% | ⚠ non-Gaussian |
| C(t) τ_relax | 20691404.3 ps (4% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.288, MSD=524.81 Å²>>Rg²=220.479) | — | OK |
| R_ee mean ± std | 33.9 ± 9.08 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0336 ± 0.0082 | <0.10 | PASS |
| Density homogeneity CV | 23.7% (6³ grid, 29.7 atoms/voxel) | <25% | PASS |

**Warnings:** MSID slope = 1.447 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 4% decayed at end of trajectory (τ_relax=20691404.3 ps vs T_traj=1951.0 ps)