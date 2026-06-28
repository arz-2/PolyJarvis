## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=299.99 K · 951 frames analysed (skip=50) · 2026-06-22 03:40

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.012% (p=0.7055) | <1%, p<0.01 | PASS |
| Energy drift | 1.2683% (p=0.0) | <1%, p<0.01 | FAIL |
| Density block-SEM | 0.0311% | <1% | PASS |
| Energy block-SEM | 0.1861% | <1% | PASS |
| τ_eff density | 0.1% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.8% | <30% | PASS |
| MSID slope | 1.276 (R²=0.9871) | 1.0 ±20% | ⚠ non-Gaussian |
| C(t) τ_relax | 33640.2 ps (2% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.423, MSD=802.6 Å²>>Rg²=726.415) | — | OK |
| R_ee mean ± std | 61.35 ± 20.92 Å (N=20 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0173 ± 0.0047 | <0.10 | PASS |
| Density homogeneity CV | 12.9% (6³ grid, 22.4 atoms/voxel) | <25% | PASS |

**Warnings:** MSID slope = 1.276 (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension; C(t) partially decayed: 2% decayed at end of trajectory (τ_relax=33640.2 ps vs T_traj=951.0 ps)