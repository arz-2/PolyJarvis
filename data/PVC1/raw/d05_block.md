## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=529.77 K · 1951 frames analysed (skip=50) · 2026-06-20 08:42

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0% (p=nan) | <1%, p<0.01 | N/A (NVT — fixed volume) |
| Energy drift | 0.0545% (p=0.8758) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0% | <1% | N/A (NVT — fixed volume) |
| Energy block-SEM | 0.0569% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 30.4% | <30% | FAIL |
| MSID slope | 1.317 (R²=0.9871) | 1.0 ±20% | ⚠ non-Gaussian |
| C(t) τ_relax | 3618757684.0 ps (0% decayed) | — | ⚠ partial |
| MSD kinetic trap | yes (α=0.272, MSD=222.58 Å²>>Rg²=292.127) | — | ⚠ trapped |
| R_ee mean ± std | 40.38 ± 17.84 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0252 ± 0.0039 | <0.10 | PASS |
| Density homogeneity CV | 16.6% (5³ grid, 29.0 atoms/voxel) | <25% | PASS |

**Warnings:** MSID slope = 1.317 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 0% decayed at end of trajectory (τ_relax=3618757684.0 ps vs T_traj=1951.0 ps); MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state