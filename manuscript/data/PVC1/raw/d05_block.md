## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.97 K · 951 frames analysed (skip=50) · 2026-07-02 16:05

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.6496% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 5.8583% (p=0.0002) | <1%, p<0.01 | FAIL |
| Density block-SEM | 0.0849% | <1% | PASS |
| Energy block-SEM | 1.0731% | <1% | FAIL |
| τ_eff density | 0.2% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 20.7% | <30% | PASS |
| MSID slope | 1.276 (R²=0.9835) | 1.0 ±20% | ⚠ non-Gaussian |
| C(t) τ_relax | 9766.4 ps (14% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.428, MSD=970.06 Å²>>Rg²=243.153) | — | OK |
| R_ee mean ± std | 33.57 ± 13.0 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0207 ± 0.0068 | <0.10 | PASS |
| Density homogeneity CV | 18.7% (5³ grid, 29.0 atoms/voxel) | <25% | PASS |

**Warnings:** MSID slope = 1.276 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 14% decayed at end of trajectory (τ_relax=9766.4 ps vs T_traj=951.0 ps)