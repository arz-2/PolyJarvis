## D-05 CONVERGENCE DETAIL
`check_equilibration_comprehensive` · T=300.05 K · 951 frames analysed (skip=50) · 2026-06-26 18:44

**Overall: FAIL**

### A. Thermo convergence
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Density drift | 0.0227% (p=0.6253) | <1%, p<0.01 | PASS |
| Energy drift | 0.0093% (p=0.8421) | <1%, p<0.01 | PASS |
| Density block-SEM | 0.0285% | <1% | PASS |
| Energy block-SEM | 0.0097% | <1% | PASS |
| τ_eff density | 0.0% of trajectory | — | OK |

### B. Chain conformation
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| Rg CV (chain–chain) | 21.4% | <30% | PASS |
| MSID slope | 1.172 (R²=0.9779) | 1.0 ±20% | OK |
| C(t) τ_relax | 45336.2 ps (7% decayed) | — | ⚠ partial |
| MSD kinetic trap | no (α=0.271, MSD=553.68 Å²>>Rg²=243.36) | — | OK |
| R_ee mean ± std | 34.46 ± 18.65 Å (N=10 chains) | — | INFO |

### C. Spatial / packing
| Check | Value | Threshold | Result |
|-------|-------|-----------|--------|
| P2 nematic order | 0.0184 ± 0.0053 | <0.10 | PASS |
| Density homogeneity CV | 23.6% (6³ grid, 20.9 atoms/voxel) | <25% | PASS |

**Warnings:** C(t) partially decayed: 7% decayed at end of trajectory (τ_relax=45336.2 ps vs T_traj=951.0 ps)