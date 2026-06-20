# Bulk Modulus Extractor — Memory Index

- [PHYC PE exp_K_range anomaly](project_phyc_exp_k_range.md) — exp_K_range=[0.3,0.8] GPa in polymer_rules is likely wrong for polyhydrocarbon bulk modulus; PE1 Murnaghan B0=1.46 GPa, fluctuation B_dyn=1.59 GPa, both well above range
- [PHYC rubbery B0_prime high](project_phyc_murnaghan_b0prime.md) — TraPPE-UA PE at 300 K gives B0'~13.5, nonlinear EOS; B_def cross-check unreliable (R²<0.05); use Murnaghan EOS path only for PHYC
- [Deform script graphs_dir bug](feedback_deform_graphs_dir.md) — extract_bulk_modulus_deform.py rejects --graphs_dir; MCP tool silently fails (completed sentinel but no output files); fix: re-run script directly without --graphs_dir [ingested 2026-06-20]
