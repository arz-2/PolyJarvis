# Operator intervention — PLLA_1, 2026-09-09

## What was done and why

At 07:37 UTC the PLLA_1 orchestrator (pid 3582393) was terminated by the operator with SIGTERM
while it was inside the melt gate's `check_equilibration_comprehensive` call. It was killed
deliberately, before it could record a failure, to escape a harness defect rather than a
scientific one.

The defect: `mcp-servers/mcp-lammps-engine/server.py:3284`, `_run_extract_equilibrated_density`,
did not accept the `output_name` keyword its own call site at :3626 passes and its own body at
:3306 spends. Every call raised
`TypeError: _run_extract_equilibrated_density() got an unexpected keyword argument 'output_name'`.
Introduced by 71a6734 (the equilibration/cooling split) and latent for a week, because the melt
gate is the first caller to reach it and no run had completed a melt chain until sPVC_1 did at
02:58 UTC on 2026-09-09. `run_campaign.py:67` imports server.py in-process, so the already-running
orchestrators held the defective function in memory and could not pick up the fix; a restart was
the only way to load it.

## Reconstructed state

PLLA_1's equilibration chain `8d42e083` COMPLETED at 07:26:05 UTC — all ten stages, sentinel
`/tmp/polyjarvis/sentinels/done_8d42e083.json` written. `run_campaign.py:921` unlinks
`pending_equil_submission.json` immediately on chain completion, before the gate runs, so by the
time of the kill PLLA_1 had no reattach handle and a plain resume would have resubmitted the whole
chain and discarded ~11 hours of completed, healthy MD.

`attempts/equilibration/attempt-0002/pending_equil_submission.json` was therefore reconstructed by
hand, from `attempts/equilibration/attempt-0001/pending_equil_submission.json` (same run, same
plan, `input_hash` a872dabe4805e82d on both attempts, so the same protocol):

  - 73 occurrences of `equilibration/attempt-0001` rewritten to `equilibration/attempt-0002`.
    The 11 `build/attempt-0001` references were deliberately NOT rewritten — the build attempt is
    a real, shared input.
  - `chain_id` set to `8d42e083`, the chain that actually completed.
  - No `gate_phase` key; the document is the flat `{chain_id, workflow}` shape, matching the
    single-chain path this run took (10-stage run_order).

Verified before installation: all 30 file paths the reconstructed workflow names — every stage's
`script`, `input_data`, `log_file`, `output_data`, `output_restart`, plus `melt_data_path`,
`npt_production_log` and `npt_production_dir` — exist on disk, written by the completed chain.

## What this does and does not change

No simulation parameter was altered. `decided_params` and `effective_parameters` are untouched and
the attempt's `input_hash` is unchanged, so the fixed-protocol contract across replicates holds.
The intervention affects only which chain the resumed orchestrator waits on, and it makes it wait
on the one that already ran rather than launching an identical replacement.

NOTE FOR THE MANUSCRIPT: this is an operator action, not an agent recovery. It does not appear in
`recovery_log.jsonl` and must not be counted as one. The two entries there for PLLA_1 (an
`auto_remedy_rejected` on the disk preflight and one `escalation`) are the run's real recovery
record.

## Second intervention, 07:46 — the reattach was declined, and why

The first resume did NOT reattach. It minted `attempt-0003` and submitted a fresh chain
(`d289417a`); it was killed within ~90 s, during `minimize`, and the directory was removed. No
data from attempt-0002 was touched.

Cause: the melt gate's own `derive_backbone_types` call wrote `backbone_types: [1, 2, 3, 6, 7]`
into `raw/run_plan.json` at 07:25:43, ~80 seconds before the kill. On the next resume
`WorkflowEngine._reconcile_plan` compared the plan hash, saw the change, found `backbone_types` in
`stages_for(...)` for equilibration, and called `invalidate_from("equilibration", "executable plan
changed")`. The stage's `input_hash` moved a872dabe -> d8abb221, so `_new_attempt`'s reattach
predicate (`last.input_hash == input_hash`) failed and a fresh attempt was minted.

This is a genuine harness sharp edge and it is worth recording as one: a value the gate DERIVES
FROM the equilibrated cell is written back into the plan that is supposed to describe the
protocol, and that write-back invalidates the very stage that produced it. It only bites when an
orchestrator restarts between the gate's write and the stage being accepted.

Repair applied (verified, not assumed):
  - `decided_params.backbone_types` REMOVED from run_plan.json -- removed, not set to null. The
    hash is over the parameter dict, and attempt-0001's recorded parameters have no such key at
    all; setting it to null gave 029e8afb, a third distinct hash.
  - `effective_parameters.backbone_types` removed from workflow_state.json to match.
  - `plan_hash` set to the reverted plan's canonical hash so `_reconcile_plan` is a no-op.
  - the `attempt-0003` entry dropped, the `stale_reason` markers cleared from equilibration,
    cooling, thermal, mechanical and summary, and the equilibration record left at
    `status: "running"` with `input_hash` a872dabe.

Verification before writing: `WorkflowEngine._input_hash("equilibration")` was recomputed against
the repaired files, off a probe object holding the same `policy_hashes` (the three policy files are
unmodified since 2026-09-07) and the same accepted-build dependency checksums (all 11 build
artifacts re-hashed, none changed). It returns
`a872dabe4805e82dcd64837168e4ae4bb7c9643c96fe60d0b3c6486c2612e209` -- byte-identical to what
attempt-0002 recorded. The same probe reproduces d8abb221 when `backbone_types` is present, which
is what confirms the probe is faithful rather than merely agreeable.

The gate will re-derive `backbone_types` from the same cell and re-write it on the next pass.

## Third intervention, 12:05 — the agent's protocol revision was reverted

Operator decision, taken after the melt-relaxation gate itself was rebuilt. This one reverses a
recovery-agent decision, so it is recorded in full.

WHAT THE AGENT DID (escalation 2 of 2, 12:24:16 UTC): the melt gate returned EXTEND on the single
binding gate `ct` (C(t) decayed 11.5% against PEST's class threshold of 0.15). The deterministic
remedy `continue_npt` sized a continuation of 17,453.2 ns from `relaxation_time_ns` = 872.66 and was
rejected by the bounds check. The agent then returned `revise_plan` with
`nvt_melt_min_steps: 15000000` (from 5,000,000), and attempt-0003 replayed all ten stages.

WHY IT WAS REVERTED: the threshold it was sized to clear no longer exists. `ct_min_decay_melt` was
a per-BACKBONE-CLASS constant, and measured against the 36 round-1 campaigns on 2026-09-09 it was
(a) unachievable -- round-1 decay fractions span 0.004-0.158, so PEST's 0.15 would have failed 35
of 36, including every campaign whose density graded PASS at 0.0% error -- and (b) uncorrelated
with anything this campaign measures: normalised to a common 5 ns by each run's own MSD power law,
PE1 is kinetically trapped at 0.81x Rg^2 and reproduces density exactly, while PS1 sits at 3.51x
Rg^2 and still misses density by -1.9%. Every density FAIL in round-1 is chemistry-clustered
(PMMA -5.7 to -6.7%, PEEK -5.1 to -5.6%) -- PCFF systematics, not equilibration.

Melt chain relaxation now binds through `enforce_gate.chain_displacement_gate`: g3(t) >= 1.0 * Rg^2
(Auhl et al., J. Chem. Phys. 119, 12718 (2003)), per SYSTEM, from this run's own measured Rg^2,
with `kinetic_trap_flag` folded in. C(t) is still computed and reported but no longer binds.

Under that gate PLLA_1's attempt-0002 melt PASSES: MSD/Rg^2 = 3.088, kinetic_trap_flag = False.
The 6.7 GPU-hours of attempt-0003 bought nothing the campaign now requires, and the protocol frozen
for PLLA_2/PLLA_3 should be the one that actually produced a melt clearing the gate 3x over.

WHAT WAS CHANGED
  - `decided_params.nvt_melt_min_steps` REMOVED from run_plan.json (removed, not reset to
    5000000 -- attempt-0002's recorded parameters carry no such key, and the input_hash is over
    the parameter dict, so a reset value hashes differently from an absent one; the same trap as
    backbone_types in the second intervention).
  - `effective_parameters.nvt_melt_min_steps` removed to match; `plan_hash` set to the reverted
    plan's canonical hash so `_reconcile_plan` is a no-op.
  - the `attempt-0003` entry and directory removed; attempt-0002 reopened at `status: "running"`
    with its `finished_at` cleared, and the equilibration record returned to `input_hash`
    a872dabe...e209.
  - `pending_equil_submission.json` restored for attempt-0002 (chain 8d42e083, the chain that
    completed at 07:26:05; sentinel still on disk), so the resume reattaches instead of
    resubmitting.
  - attempt-0002's `raw/equilibration.json` and `raw/d05_block.md` DELETED. They were computed
    under the retired criterion; the gate must recompute them, not inherit them.

VERIFICATION before writing: `WorkflowEngine._input_hash("equilibration")` recomputed on the
reverted files returns a872dabe4805e82dcd64837168e4ae4bb7c9643c96fe60d0b3c6486c2612e209 --
byte-identical to what attempt-0002 ran under.

NOTE FOR THE MANUSCRIPT: the agent's decision was sound given the gate it was handed; what was
wrong was the gate. Both belong in the record. This is an operator action and must not be counted
as an agent recovery. PLLA_1 has now spent both of its agent escalations (disk preflight
2026-09-08, this EXTEND 2026-09-09); a further blocking finding halts the run.
