## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=549.89 K · 1951 frames analysed (skip=50) · 2026-06-20 03:39

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0% (p=1.0) | <1%, p<0.01 | N/A (NVT — fixed volume) |
| Energy drift | 0.1672% (p=0.0018) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0% | <1% | N/A (NVT — fixed volume) |
| Energy block-SEM | 0.0204% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 13.1% | <30% | PASS |
| C∞ | 203.782 | lit. varies | INFO |
| MSID slope | 1.083 (R²=0.9917) | 1.0 ±20% | OK |
| C(t) τ_relax | 4225182193.2 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=-0.004, MSD=61.6 Å²>>Rg²=161.096) | — | ⚠ trapped |
| R_ee mean ± std | 22.28 ± 9.84 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0286 ± 0.0025 | <0.10 | PASS |
| Density homogeneity CV | 22.3% (6³ grid, 27.9 atoms/voxel) | <25% | PASS |

**Warnings:** C∞ = 203.782 is outside broad expected range [3, 15] — verify backbone_types and n_backbone_bonds; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=4225182193.2 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state