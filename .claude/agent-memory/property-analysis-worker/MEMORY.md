# Property Analysis Worker Memory Index

- [PMMA4 Born K_T failure](project_pmma4_born_failure.md) — PMMA4/PACR/PCFF Born+NVT gave K_T=-21.9 GPa (unphysical); root cause: failed equilibration + under-density; block-K worsens over production window
- [Born method non-stationarity signature](feedback_born_nonstationarity.md) — Block-K values growing in magnitude over production window = non-stationary glass; fluctuation-dominated Born K diagnostic
- [generate_run_summary Born K gap](feedback_run_summary_born_gap.md) — generate_run_summary does not pick up bulk_modulus_born.json; only reads bulk_modulus.json (fluctuation method); Born K appears as "no exp ref" in summary
