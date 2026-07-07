## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.13 K · 1951 frames analysed (skip=50) · 2026-06-20 14:16

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.3844% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 0.694% (p=0.0047) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0607% | <1% | PASS |
| Energy block-SEM | 0.1801% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.6% | <30% | PASS |
| C∞ | 346.706 | lit. varies | INFO |
| MSID slope | — | 1.0 ±20% | skipped (short backbone) |
| C(t) τ_relax | — | — | insufficient frames |
| MSD kinetic trap | yes (α=0.114, MSD=45.45 Å²>>Rg²=411.124) | — | ⚠ trapped |
| R_ee mean ± std | — | — | not available |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0 ± 0.0 | <0.10 | PASS |
| Density homogeneity CV | 22.0% (7³ grid, 20.5 atoms/voxel) | <25% | PASS |

**Warnings:** C∞ = 346.706 is outside broad expected range [3, 15] — verify backbone_types and n_backbone_bonds; MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state