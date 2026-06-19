---
name: emc-seed-not-persisted
description: EMC seed=-1 does not persist the resolved packing seed; no seed field in job output, esh/in carry only LAMMPS run seeds
metadata:
  type: project
---

When `submit_emc_cell_job(seed=-1)`, the resolved EMC cell-packing RNG seed is
NOT persisted anywhere recoverable:

- `get_emc_job_output` has no `seed` field.
- `emc_build.esh` carries no seed line.
- `build.emc` and `emc_build.emc.gz` only show `seed -> -1` (the literal unresolved value).
- `emc_build.in` contains `lseed`/`vseed` (e.g. 723853 / 486234) — these are
  LAMMPS *run-script* seeds (Langevin thermostat + velocity init) for an
  equilibration step the builder does NOT run. Do NOT report these as `emc_seed`.

**How to apply:** When `seed=-1`, report `emc_seed: random (-1), resolved packing
seed not persisted by EMC server`. Do not substitute the LAMMPS run seeds. For
reproducibility-critical runs, pass an explicit positive `seed` so the value is
known up front. See [[emc-output-naming]].
