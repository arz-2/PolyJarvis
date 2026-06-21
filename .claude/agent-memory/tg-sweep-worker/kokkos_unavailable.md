---
name: kokkos_unavailable_lammps_binary
description: KOKKOS binary at /home/arz2/lammps-install-kokkos/bin/lmp; pass engine="kokkos" to run_lammps_script
metadata:
  type: project
---

**KOKKOS binary:** `/home/arz2/lammps-install-kokkos/bin/lmp` — supports `-k on g N -sf kk -pk kokkos` flags.

**How to invoke:** Pass `engine="kokkos"` to `run_lammps_script()` — the MCP tool exposes `engine: str = "gpu"` (default) which selects binary and flag set automatically.

**Standard GPU binary:** `/home/arz2/lammps-install/bin/lmp` (engine="gpu", default).

**Context:** PLA1 tg_sweep_r40 (2026-06-21) was the first KOKKOS tg-sweep run. PCFF/OPLS defaults already flip to engine=kokkos per gen_prompt plan (see [[project_kokkos_turing75]]).

**Note:** An earlier version of this memory incorrectly stated that `run_lammps_script` had no `engine` parameter. That was wrong — the parameter exists and works.
