## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.17 K · 951 frames analysed (skip=50) · 2026-06-24 05:36

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.1266% (p=0.003) | <1%, p<0.01 | PASS |
| Energy drift | 0.1415% (p=0.4663) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.027% | <1% | PASS |
| Energy block-SEM | 0.1068% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 25.4% | <30% | PASS |
| MSID slope | 1.357 (R²=0.9925) | 1.0 ±20% | ⚠ non-Gaussian |
| C(t) τ_relax | 1091062.5 ps (1% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.215, MSD=357.73 Å²>>Rg²=931.831) | — | ⚠ trapped |
| R_ee mean ± std | 73.73 ± 29.41 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0222 ± 0.0052 | <0.10 | PASS |
| Density homogeneity CV | 12.9% (6³ grid, 22.4 atoms/voxel) | <25% | PASS |

**Warnings:** MSID slope = 1.357 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 1% decayed at end of trajectory (τ_relax=1091062.5 ps vs T_traj=951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state