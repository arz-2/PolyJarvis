---
name: emc-params-cutoff-mismatch
description: EMC writes cutoff/charge_cutoff 9.5 A into emc_build.params regardless of the prompt's cutoff_A; report the mismatch, never rebuild
metadata:
  type: feedback
---

`submit_emc_cell_job` has no cutoff parameter — EMC always writes
`variable cutoff index 9.5` and `variable charge_cutoff index 9.5` into `emc_build.params`,
even when the orchestrator's prompt specifies `cutoff_A: 12.0`. Report the divergence in the
final message; do not treat it as a build failure and do not resubmit.

**Why:** Topology, box size, and coefficients are cutoff-independent, so `cell.data` is
correct either way. But `emc_build.params` ships next to it and the equilibration worker may
`include` it, silently running at 9.5 A instead of the planned value. The builder cannot fix
this — only the equilibration deck can override.

**How to apply:** After copying files, grep the params file for `cutoff` and, if it disagrees
with the prompt's `cutoff_A`, add one line to the final message: params sets X A, planned Y A,
equilibration must override or accept. Same check applies to every EMC class.
Related: [[pktn_routing]], [[feedback_output_contract_footguns]].
