---
name: pla1-cooldown-chain
description: PLA1 glassy PEST/PCFF cooldown-tail submission after melt-mixing gate PASS
metadata:
  type: project
---

PLA1 (PEST/PCFF, glassy, T_workflow=620K) melt phase passed the melt-mixing gate.
Cooldown tail (npt_cool300 + npt_prod300, 2 stages) read back verbatim from
`_pending_cooldown_stages.json` and submitted without regenerating the workflow.
chain_id=7fb2ac17; engine=kokkos, gpu_ids=2, mpi=1.
Verified `read_data` baked into `npt_cool300.in` matched the pending JSON's `input_data`
(`npt_production_out.data`) before submitting — see [[feedback_stale_cooldown_pending_after_melt_extend]]
for why this check matters (repointing JSON alone is a no-op if the .in disagrees).

**Why:** confirms the melt→cooldown split (glassy `phase=melt`/`phase=cooldown`) works cleanly
when no extend/recovery cycle intervened — the saved JSON was still consistent with its .in files.
**How to apply:** for any PLA/PEST cooldown resubmission, always diff `input_data` in the JSON
against the `.in`'s `read_data` line first; only skip that check when neither the melt data file
nor `_pending_cooldown_stages.json` was touched since the melt chain finished.
