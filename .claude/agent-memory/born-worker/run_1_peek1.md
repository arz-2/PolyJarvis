---
name: run_1_peek1_born_submission
description: PEEK1 NVT Born matrix submission (run_id 0b5a1c8c) — GPU 3, PCFF, 4 ns, compute born/matrix numdiff verified
metadata:
  type: project
---

**PEEK1 Stage 8 Born Submission — 2026-06-20**

- **run_id:** 0b5a1c8c
- **polymer:** PEEK1 (PKTN, glassy)
- **is_glassy:** true (exp Tg 418 K)
- **input:** npt_prod300_out.data (300 K, 4096 atoms)
- **N_STEPS:** 4,000,000 (4.0 ns at 1.0 fs dt)
- **GPU:** 3 (co-located with Tg sweep, mpi=1)
- **FF:** PCFF (use_pcff=true)
- **born_matrix_file:** /home/arz2/PolyJarvis/data/PEEK1/lammps/mechanical/08_nvt_born/born_matrix.dat

**Template validation:**
- EXTRA-COMPUTE present: ✓ (born/matrix in lmp -h)
- numdiff syntax: ✓ (virial_compute_ID=born_press at line 99)
- K_T indices: ✓ (C12/C13/C23 at [7]/[8]/[12], lines 103–105)
- use_gpu=false, CPU run: ✓

**Next:** Orchestrator owns Monitor. bulk-modulus-extractor will read born_matrix.dat after run completes.
