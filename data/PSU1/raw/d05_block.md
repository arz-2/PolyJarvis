## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=699.9 K · 1951 frames analysed (skip=50) · 2026-06-20 00:09

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0% (p=1.0) | <1%, p<0.01 | N/A (NVT — fixed volume) |
| Energy drift | 0.0467% (p=0.4404) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0% | <1% | N/A (NVT — fixed volume) |
| Energy block-SEM | 0.0139% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 26.2% | <30% | PASS |
| C∞ | 53.223 | lit. varies | INFO |
| MSID slope | 0.964 (R²=0.9967) | 1.0 ±20% | OK |
| C(t) τ_relax | 1776439999.6 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.022, MSD=102.15 Å²>>Rg²=841.486) | — | ⚠ trapped |
| R_ee mean ± std | 69.42 ± 35.79 Å (N=8 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0139 ± 0.0022 | <0.10 | PASS |
| Density homogeneity CV | 20.2% (7³ grid, 25.2 atoms/voxel) | <25% | PASS |

**Warnings:** C∞ = 53.223 is outside broad expected range [3, 15] — verify backbone_types and n_backbone_bonds; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=1776439999.6 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state