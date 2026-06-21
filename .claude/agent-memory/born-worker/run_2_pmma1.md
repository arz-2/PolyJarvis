---
name: run_2_pmma1_born_submission
description: PMMA1 NVT Born matrix submission (run_id bb096bff) — MPI=4 CPU, PCFF, 0.5 ns, 6020 atoms, glassy Tg=340 K
ingested_at: 2026-06-21
metadata:
  type: project
---

**PMMA1 Stage 8 Born Submission — 2026-06-21**

- **run_id:** bb096bff
- **polymer:** PMMA1 (PACR, glassy)
- **is_glassy:** true (exp Tg 340 K > 300 K)
- **input:** npt_prod300_out.data (300 K, 6020 atoms, ρ=1.1158 g/cm³)
- **N_STEPS:** 500,000 (0.5 ns at 1.0 fs dt)
- **GPU/MPI:** CPU MPI=4 (use_gpu=false), GPU 1 co-located
- **FF:** PCFF (use_pcff=true, class2 bonds/angles/dihedrals/impropers)
- **born_matrix_file:** /home/arz2/PolyJarvis/data/PMMA1/lammps/mechanical/08_nvt_born/born_matrix.dat
- **est_runtime:** 3–4 hours (PCFF+PPPM overhead, 6k atoms)

**Template validation (PMMA-specific):**
- EXTRA-COMPUTE present (line 99: numdiff 0.0001 born_press) ✓
- virial_compute_ID in 3rd arg position ✓
- K_Born indices: C11/C22/C33 at [1/2/3], C12/C13/C23 at [7/8/12] ✓
- PPPM 1e-6 (tight kspace) ✓
- SHAKE constraints applied (m 1.008) ✓
- use_gpu=false, CPU run (consistent with stress-fluctuation accuracy requirement) ✓
- Thermo includes pxx/pyy/pzz for Var(P) calculation ✓

**Next:** Orchestrator owns Monitor. bulk-modulus-extractor will read born_matrix.dat after run completes (status == RUN_COMPLETE).
