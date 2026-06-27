# D-06b — Multirate Tg Aggregation (PEEK2)

## Registry Summary
- **Polymer:** PKTN (PEEK)
- **Run name:** PEEK2
- **Registry path:** `/home/arz2/PolyJarvis/data/_tg_registry/PKTN__Oc1ccc_Oc2ccc_C_O_c3ccc_cc3__cc2__cc1.csv`

## Valid Rates
| Rate (K/ns) | Tg_MD (K) | R² | Fit Quality | Replicate | Timestamp |
|---|---|---|---|---|---|
| 40 | 523.6 | 0.9967 | EXCELLENT | 1 | 2026-06-23T10:13:32Z |

**Total valid points:** 1 (< 2 minimum for log-linear fit)

## Multirate Fit Status
- **n_rates_valid:** 1
- **rates_span_decades:** N/A (single point)
- **multirate_method:** single_rate_fallback
- **multirate_r_squared:** N/A
- **loglinear_slope_K:** N/A

### Fallback Rationale
Rates 160 K/ns and 400 K/ns failed to produce acceptable fits due to degenerate transition widths (c → 0) arising from fast-rate undersampling of the rigid PEEK backbone. Only the 40 K/ns rate yielded sufficient plateau resolution for a reliable bilinear fit (R² = 0.9967, fit_quality = EXCELLENT).

## Reported Results

### Tg
- **tg_md_K:** 523.6 (at 40 K/ns)
- **tg_dsc_equiv_K:** null (cannot extrapolate; insufficient rate coverage)

### Thermal Properties (from rate 40 K/ns analysis)
| Property | Glassy | Rubbery |
|---|---|---|
| CTE (α) | 1.965e-4 K⁻¹ | 4.274e-4 K⁻¹ |
| Slope (H vs. T) | 68.47 kcal/(mol·K) | 70.51 kcal/(mol·K) |

### Enthalpy
- **ΔCp:** 0.0923 J/(g·K)
- **ΔCp_status:** success
- **H_fit_r_squared:** 0.9893
- **H_fit_quality:** GOOD

## Recommendation
With only one acceptable rate, the multirate Arrhenius extrapolation cannot be performed. The reported **Tg_MD = 523.6 K (at 40 K/ns)** is the best available estimate. Users should interpret this as a single-rate measurement; DSC-equivalent prediction requires additional rates spanning ≥2 decades in cooling rate.

---
Generated: 2026-06-23
