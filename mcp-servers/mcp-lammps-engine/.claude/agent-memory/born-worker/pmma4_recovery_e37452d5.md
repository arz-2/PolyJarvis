---
name: pmma4_born_recovery_e37452d5
description: PMMA4 NVT Born matrix run submitted after template fix; CPU-only with manual script
metadata:
  type: project
---

**Run ID:** e37452d5
**Polymer:** PMMA4 (PACR, n_atoms=5264)
**Script:** /home/arz2/PolyJarvis/data/PMMA4/lammps/prop/08_nvt_born/08_nvt_born.in
**Status:** submitted 2026-06-16

**Recovery context:**
- Previous attempt failed: "Illegal compute born/matrix command"
- Root causes fixed:
  1. Missing virial_compute_ID in `compute born/matrix numdiff` 
  2. Incorrect 2D array indexing for born_matrix variables
- Template nvt_born not in template list (planned but not implemented)
- Generated script manually with corrected `compute born_press all pressure thermo_temp` + `compute born_matrix all born/matrix numdiff 0.0001 born_press`
- EXTRA-COMPUTE confirmed in lmp binary

**Parameters:**
- 4 ns NVT at 300 K, 4M steps, dt=1 fs
- born/matrix numdiff delta=0.0001, output every 1 ps (100 samples/output)
- CPU-only (use_gpu=False), MPI=4 ranks (GPU IDs 0,1,2,3 available but not used for compute)
- PCFF forcefield
- PPPM kspace

**Expected outputs:**
- born_matrix.dat: elastic tensor averages
- 08_nvt_born.log: thermo with pressure columns
- 08_nvt_born_out.data: final structure
