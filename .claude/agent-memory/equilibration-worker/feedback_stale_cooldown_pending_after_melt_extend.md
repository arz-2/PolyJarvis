---
name: stale-cooldown-pending-after-melt-extend
description: pending_cooldown_stages.json first-stage input_data can go stale if the melt phase gets extended after the file was saved
metadata:
  type: feedback
---

`_pending_cooldown_stages.json` is written once when the melt-phase chain is split (at
`npt_production`). If the melt gate later fails and the orchestrator runs an `npt_extend` stage
before re-gating, the saved cooldown JSON's first stage (`npt_cool300`/equivalent) still points
its `input_data` at the old `npt_production_out.data`, not the newer extended checkpoint.

**Why:** the cooldown-phase instructions explicitly forbid re-calling
`generate_equilibration_workflow` (it would rebuild the whole chain from scratch), so the only
fix point is patching the stale path by hand before submission — the orchestrator must supply the
new checkpoint path since the worker has no way to discover it from `phase=cooldown` inputs alone.

**How to apply:** on `phase=cooldown`, if the orchestrator prompt calls out a moved/extended melt
checkpoint, `Read` the pending-cooldown JSON, diff the first stage's `input_data` against the
stated current checkpoint path, and `Edit` only that one field — leave stage names, temperatures,
step counts, and every other field untouched. Verify the new checkpoint `.data` file actually
exists via `ls` before submitting (caught here: PEEK1, `npt_extend_out.data` did exist, 2026-08-11).
Report whether a repoint happened in the RESULT block (`repointed_first_stage`).

**Correction (PEEK1 resubmit, 2026-08-11):** editing the JSON's `input_data` field alone is a
no-op — `run_lammps_chain` launches `lmp -in <script>.in`, and the actual `read_data` path is
baked into that `.in` file at generation time, not read from the JSON at submit time. A prior
cooldown chain (ddfcab11) was killed after 2 min because only the JSON had been repointed while
the `.in` file still `read_data`'d the stale path. The real fix is `grep -n read_data` on both
`.in` files and `Edit` the `read_data` line directly (or confirm the orchestrator already patched
it) — then verify the JSON's `input_data`/`output_data` fields agree, since both must match for
the chain to be self-consistent. Always `grep read_data` on every stage `.in` file immediately
before submitting a cooldown/resubmit chain, even when the JSON looks already correct.

See [[project_pmma1_equil_chain]] for the split melt/cooldown submission pattern this extends.
