# Property Analysis Worker Memory Index

- [PE/PHYC TraPPE-UA energy drift at 300K](feedback_pe_energy_drift_300k.md) — Energy drift >2% at 300K NPT is a recurring pattern for PE; density and K still reliable [ingested 2026-06-10]
- [check_equilibration_comprehensive: no graphs_dir](feedback_equil_check_no_graphs_dir.md) — Script now accepts --graphs_dir (added to argparse 2026-06-10); fix applied to check_equilibration_comprehensive.py [ingested 2026-06-10]
- [Equilibration check quirks](equilibration_check_quirks.md) — NPT-mislabelled-as-NVT and PE C∞ borderline warning are benign; Rg CV flag at 300K is soft concern [ingested 2026-06-05]
- [Script bugs in PSIL analysis](feedback_script_bugs_psil.md) — check_equilibration_comprehensive NameError (ct_min_decay) fixed 2026-06-10; extract_equilibrated_density has no --graphs_dir [ingested 2026-06-10]
- [PSIL density homogeneity borderline FAIL](feedback_psil_density_homogeneity.md) — PDMS1 homogeneity CV=26.5% vs 25% threshold is marginal; thermo gates all pass; flag WARNING not FAIL [ingested 2026-06-10]
- [PAMD/Nylon deform on melt-density structure](feedback_deform_on_melt_density.md) — Deform from 650K melt endpoint gives K<0 and R²≈0; must start from 300K NPT-densified config [ingested 2026-06-10]
- [PMMA4 550K equil C(t) non-decay and MSD trap](feedback_pmma4_equil_550k.md) — C(t)/MSD kinetic trap at 550K melt (T>>Tg_exp=390K) is anomalous unlike the benign 300K case; flag EXTEND [ingested 2026-06-10]
- [Nylon1 NPT prod300 MPI log corruption](feedback_nylon1_log_corruption.md) — MPI-interleaved log line breaks extract_equilibrated_density; parser fix applied 2026-06-12 [ingested 2026-06-12]
- [Volume drift biases K downward (NPT fluctuation method)](feedback_volume_drift_biases_K.md) — Volume drift inflates Var(V) → K_T biased low; re-run eq_fraction=0.25; bracket with block mean; flag WARNING [ingested 2026-06-12]
