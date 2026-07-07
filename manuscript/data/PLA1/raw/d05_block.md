## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.05 K · 951 frames analysed (skip=50) · 2026-06-20 16:28

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1846% (p=0.0001) | <1%, p<0.01 | PASS |
| Energy drift | 0.0079% (p=0.8704) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0488% | <1% | PASS |
| Energy block-SEM | 0.0103% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 14.6% | <30% | PASS |
| MSID slope | 1.271 (R²=0.9916) | 1.0 ±20% | ⚠ non-Gaussian |
| C(t) τ_relax | 2830169.2 ps (7% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.258, MSD=417.38 Å²>>Rg²=295.023) | — | OK |
| R_ee mean ± std | 38.02 ± 12.49 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0207 ± 0.0047 | <0.10 | PASS |
| Density homogeneity CV | 23.8% (6³ grid, 20.9 atoms/voxel) | <25% | PASS |

**Warnings:** MSID slope = 1.271 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 7% decayed at end of trajectory (τ_relax=2830169.2 ps vs T_traj=951.0 ps)