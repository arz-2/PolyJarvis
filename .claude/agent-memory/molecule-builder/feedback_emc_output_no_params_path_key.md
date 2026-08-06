---
name: emc-output-no-params-path-key
description: get_emc_job_output result has no params_path key — build emc_build.params path from output_dir; EMC .data carries no Pair Coeffs, the params file does
metadata:
  type: feedback
---

`get_emc_job_output(job_id)["result"]` returns only
`status, data_path, output_dir, smiles, field, dp, density, natoms, resolved_seed,
lammps_flags, message`. The MOLECULE_BUILDER guide's `out["result"]["params_path"]`
does **not** exist — reading it raises/None-s out even on a fully successful build.

**Why:** the RESULT block requires a non-null `emc_params_path` on the EMC route, so a
literal read of the guide silently reports "no params file" when one was written.

**How to apply:** take `emc_build.params` from `result["output_dir"]` (it sits beside
`emc_build.data`; verified present for PHAL/opls-aa, `data/PVDF1`). Also note the EMC
`.data` file has **no `Pair Coeffs` section at all** — only `Masses` with OPLS type
comments (`c4`, `f1`, `h1`). All pair/bond/angle coeffs live in `emc_build.params`, so
that file is load-bearing for equilibration, not an optional extra. Sanity-check
`natoms` against dp x nchains x repeat-unit atoms + 2 caps/chain (PVDF: 10 x (60x6+2)
= 3620) to confirm `nchains` was honored rather than being resized from `ntotal`.
See [[workdir-double-cell-path]], [[emc-binary-annual-expiry]].
