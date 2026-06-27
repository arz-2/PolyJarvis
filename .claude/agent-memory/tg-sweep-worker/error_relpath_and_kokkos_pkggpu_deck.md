---
name: error_relpath_and_kokkos_pkggpu_deck
description: Two tg-sweep deck failures that each cost a retry on PSU3 — relative read_data path and a stray `package gpu` line on the kokkos engine
metadata:
  type: feedback
---

On PSU3 (PSFO/PCFF, kokkos) two separate Tg-sweep submissions each failed instantly and cost a retry. Both are deck-generation issues, not physics.

**1. Relative `read_data` path (R-01).** `gen_prompt.py --stage tg --data_path data/PSU3/...` echoes the path back **relative**, and the worker passed it verbatim to `generate_script(data_file=...)`. The generated `.in` then has `read_data data/PSU3/lammps/equil/.../npt_extend_out.data`, but `run_lammps_script` runs from the per-rate `work_dir` (`.../thermal/tg_sweep_r25`), so LAMMPS can't resolve it → `ERROR: Cannot open file ... No such file or directory` at read_data. Fix: always pass an **absolute** `data_file` to generate_script; grep the rendered `.in` for `read_data` and confirm it's absolute before submitting.

**2. `package gpu 1 neigh no` rendered on the kokkos engine (R-02).** On the r50 sweep, generate_script rendered an active `package gpu 1 neigh no` at the deck's GPU_PACKAGE slot instead of the kokkos comment `# KOKKOS: package loaded via -pk kokkos on the command line`. KOKKOS loads its package via `-pk kokkos` on the CLI and the gpu package isn't compiled into the kokkos binary → `ERROR: Package gpu command without GPU package installed`, instant fatal. The r25 deck (same params) rendered correctly, so generate_script is **inconsistent** about threading engine=kokkos into the GPU_PACKAGE block. Fix/guard: after generate_script, `sed -i 's|^package gpu .*$|# KOKKOS: package loaded via -pk kokkos on the command line|'` the `.in` and grep to confirm no active `package gpu` line remains before submitting (only when engine=kokkos).

How to apply: in the THERMAL_SWEEP worker guide (and any generate_script caller for kokkos), make "absolute data_file + grep read_data" and "strip stray `package gpu` for kokkos" mandatory pre-submit checks. Root fix belongs in `generate_script`: emit absolute read_data when given absolute, and never emit an active `package gpu` line when engine=kokkos. Repo-relative artifacts: `data/PSU3/lammps/thermal/tg_sweep_r{25,50,100}/`.
