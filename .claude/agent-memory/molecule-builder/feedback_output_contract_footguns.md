---
name: output-contract-footguns
description: Two ways to get the molecule-builder output contract wrong — double-nesting the cell dir, and dropping use_trappe from lammps_flags by copying the RESULT template literally
metadata:
  type: feedback
---

Copy build artifacts to `{work_dir}` directly, and report `lammps_flags` verbatim from the tool
result rather than from the RESULT template.

**Why:** two spec conflicts in the prompt itself, both silent if you follow the prompt literally.

1. The agent prompt says "save under `{work_dir}/cell/`", but the orchestrator already passes a
   `work_dir` ending in `/cell` (e.g. `/home/arz2/PolyJarvis/data/cis-PBD1/cell`). Following it
   literally yields `.../cell/cell/cell.data`, which no downstream worker looks for. The guide's
   "copy directly into `{work_dir}`" is the correct mechanics.
2. The RESULT template shows `lammps_flags: {"use_pcff": false, "use_opls": false}` — only two keys.
   `submit_emc_cell_job` returns a third key for TraPPE classes: `{"use_pcff": false,
   "use_opls": false, "use_trappe": true}` (seen on PDIE). That third key is the only TraPPE routing
   signal downstream gets; transcribing the two-key template drops it.

**How to apply:** on every EMC build — `mkdir -p {work_dir}` then copy to `{work_dir}/cell.data` and
`{work_dir}/emc_build.params`, never appending another `/cell`. Paste `out["result"]["lammps_flags"]`
into the RESULT block as returned, treating the template as shape-only. Also note `cell.data` from
EMC carries no inline `Pair Coeffs` — coefficients live only in `emc_build.params`, so both files
must be reported. See [[pdie-routing]], [[pest_routing]].
