## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=769.69 K · 1951 frames analysed (skip=50) · 2026-06-19 05:17

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0% (p=nan) | <1%, p<0.01 | N/A (NVT — fixed volume) |
| Energy drift | 0.0342% (p=0.7515) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0% | <1% | N/A (NVT — fixed volume) |
| Energy block-SEM | 0.0241% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 20.0% | <30% | PASS |
| MSID slope | 1.095 (R²=0.9907) | 1.0 ±20% | OK |
| C(t) τ_relax | 1878759648.1 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.095, MSD=83.2 Å²>>Rg²=568.775) | — | ⚠ trapped |
| R_ee mean ± std | 54.99 ± 19.8 Å (N=8 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0382 ± 0.0029 | <0.10 | PASS |
| Density homogeneity CV | 15.1% (5³ grid, 32.8 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=1878759648.1 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state