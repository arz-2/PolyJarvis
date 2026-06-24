# Bulk Modulus Extractor — Memory Index

- [Born SEM Inflation](born_sem_inflation.md) — Born+NVT SEM >> K_Born when fluctuation correction ~= K_Born; K_Born-Kfluc cancellation; check V_std=0 and tau_eff diagnostic
- [Born V_std=0 NVT Artefact](born_vstd_zero.md) — NVT volume is fixed (NVT ensemble), V_std=0 is expected; Born fluctuation correction uses P variance not V variance
- [PVC/PVNL Murnaghan B0' high](project_pvc_murnaghan_b0prime.md) — ±1000 atm gives B0'=16; widened to [-1000,0,1500,3000,5000] atm gives B0'=9.5, R²=0.999, K=2.80 GPa — still ~30% below exp 4.0 GPa (PCFF systematic); B_dyn=2.93 GPa consistent [updated 2026-06-24]
- [PSTR Murnaghan B0' high (screening grade)](project_pstr_murnaghan_b0prime.md) — PCFF PS ±1000 atm gives B0'~13.5, R²=0.9998, B0=2.44 GPa; 26% below exp [3.3,4.0] due to DP=40<<Me; B_dyn=2.50 GPa (2.3% agree); WARNING not FAIL [ingested 2026-06-23]
- [PEG3 Murnaghan B0'=1 anomaly (POXI/rubbery)](project_peg3_murnaghan_b0prime.md) — 0–1000 atm too narrow for rubbery PEO; B0'=1.0 (unphysical clamp), R²=0.9965; K=3.61 GPa vs B_dyn=2.73 GPa; widen to ≥1.5 GPa for physical B0'
