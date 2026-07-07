## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.01 K · 1951 frames analysed (skip=50) · 2026-06-20 21:00

**Overall: PASS**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0206% (p=0.6863) | <1%, p<0.01 | PASS |
| Energy drift | 0.1141% (p=0.2428) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.013% | <1% | PASS |
| Energy block-SEM | 0.0205% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 11.6% | <30% | PASS |
| C∞ | 14.325 | lit. varies | INFO |
| MSID slope | — | 1.0 ±20% | skipped (short backbone) |
| C(t) τ_relax | — | — | insufficient frames |
| MSD kinetic trap | no (α=0.221, MSD=630.06 Å²>>Rg²=220.829) | — | OK |
| R_ee mean ± std | — | — | not available |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0 ± 0.0 | <0.10 | PASS |
| Density homogeneity CV | 23.7% (6³ grid, 29.7 atoms/voxel) | <25% | PASS |