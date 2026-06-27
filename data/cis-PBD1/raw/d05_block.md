## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.05 K · 1451 frames analysed (skip=50) · 2026-06-19 21:20

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0% (p=1.0) | <1%, p<0.01 | N/A (NVT — fixed volume) |
| Energy drift | 0.3615% (p=0.0001) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0% | <1% | N/A (NVT — fixed volume) |
| Energy block-SEM | 0.0551% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 16.9% | <30% | PASS |
| C∞ | 15.029 | lit. varies | INFO |
| MSID slope | 1.016 (R²=0.9749) | 1.0 ±20% | OK |
| C(t) τ_relax | 71518.1 ps (4% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.396, MSD=557.54 Å²>>Rg²=588.111) | — | ⚠ trapped |
| R_ee mean ± std | 54.34 ± 18.13 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0134 ± 0.0036 | <0.10 | PASS |
| Density homogeneity CV | 12.8% (7³ grid, 23.4 atoms/voxel) | <25% | PASS |

**Warnings:** C∞ = 15.029 is outside broad expected range [3, 15] — verify backbone_types and n_backbone_bonds; C(t) partially decayed: 4% decayed at end of trajectory (τ_relax=71518.1 ps vs T_traj=1451.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state