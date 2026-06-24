# Bulk Modulus Extractor — Memory Index

- [PHYC PE exp_K_range corrected](project_phyc_exp_k_range.md) — polymer_rules PHYC exp_K_GPa corrected to [1.5,2.0]; PE1 B0=1.46, PE2 B0=1.64 both within range; old [0.3,0.8] conflated shear/bulk modulus [updated 2026-06-22]
- [PHYC rubbery B0_prime high](project_phyc_murnaghan_b0prime.md) — TraPPE-UA PE at 300 K gives B0'~13.5, nonlinear EOS; B_def cross-check unreliable (R²<0.05); use Murnaghan EOS path only for PHYC [ingested 2026-06-20]
- [Deform script graphs_dir bug](feedback_deform_graphs_dir.md) — extract_bulk_modulus_deform.py rejects --graphs_dir; MCP tool silently fails (completed sentinel but no output files); fix: re-run script directly without --graphs_dir [ingested 2026-06-20]
- [PEST/PLA Murnaghan B0' collapse at narrow pressure span](project_pest_murnaghan_b0prime_narrow.md) — ±1000 atm (±0.1 GPa) gives B0'=1.0 (degenerate fit); K=4.58 GPa corroborated by fluctuation B_dyn=4.54 GPa; recommend wider pressure span for future PEST murnaghan runs [ingested 2026-06-22]
- [Born SEM Inflation](born_sem_inflation.md) — Born+NVT SEM >> K_Born when fluctuation correction ~= K_Born; K_Born-Kfluc cancellation; check V_std=0 and tau_eff diagnostic
- [Born V_std=0 NVT Artefact](born_vstd_zero.md) — NVT volume is fixed (NVT ensemble), V_std=0 is expected; Born fluctuation correction uses P variance not V variance
- [PVC/PVNL Murnaghan B0' high](project_pvc_murnaghan_b0prime.md) — PCFF PVC ±1000 atm gives B0'~16, R²=0.998, K=2.91 GPa (exp 4.0 GPa); B_dyn=2.71 GPa consistent; widen pressure span or use deform fallback [ingested 2026-06-23]
- [PSTR Murnaghan B0' high (screening grade)](project_pstr_murnaghan_b0prime.md) — PCFF PS ±1000 atm gives B0'~13.5, R²=0.9998, B0=2.44 GPa; 26% below exp [3.3,4.0] due to DP=40<<Me; B_dyn=2.50 GPa (2.3% agree); WARNING not FAIL [ingested 2026-06-23]
