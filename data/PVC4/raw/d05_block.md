## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.0 K · 951 frames analysed (skip=50) · 2026-06-24 23:44

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.9393% (p=0.0) | <1%, p<0.01 | PASS |
| Energy drift | 9.5613% (p=0.0) | <1%, p<0.01 | FAIL |
| Density block-SEM | 0.1098% | <1% | PASS |
| Energy block-SEM | 1.0155% | <1% | FAIL |
| τ_eff density | 0.2% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 18.1% | <30% | PASS |
| C∞ | 2.905 | lit. varies | INFO |
| MSID slope | 1.209 (R²=0.9689) | 1.0 ±20% | ⚠ non-Gaussian |
| C(t) τ_relax | 14387.5 ps (16% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.264, MSD=563.96 Å²>>Rg²=205.553) | — | OK |
| R_ee mean ± std | 28.76 ± 11.99 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0271 ± 0.008 | <0.10 | PASS |
| Density homogeneity CV | 18.5% (5³ grid, 29.0 atoms/voxel) | <25% | PASS |

**Warnings:** C∞ = 2.905 is outside broad expected range [3, 15] — verify backbone_types and n_backbone_bonds; MSID slope = 1.209 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 16% decayed at end of trajectory (τ_relax=14387.5 ps vs T_traj=951.0 ps)