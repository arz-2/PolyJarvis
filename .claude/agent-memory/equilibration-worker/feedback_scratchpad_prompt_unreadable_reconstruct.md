---
name: feedback_scratchpad_prompt_unreadable_reconstruct
description: Orchestrator pointed to a scratchpad .txt "full stage prompt" and guides/EQUILIBRATION.md, both denied by the context-boundary hook; reconstructed params from run_plan.json + run_log.md + agent-memory instead
metadata:
  type: feedback
  ingested_at: 2026-08-12
---

The launching message referenced `/tmp/.../scratchpad/equil_cmp.txt` as "your full stage prompt,
read it FIRST" and separately `guides/EQUILIBRATION.md` — both `Read` and even a `Bash ls` on
`guides/` were denied by the PreToolUse context-boundary hook ("outside your allowed context").
This is not an injection attempt to route around; per [[project_gate_taxonomy_shipped]]-era
context-boundary work (commit 76df9fa, "enforce per-agent context boundary via PreToolUse hook"),
the guide is normally inlined into the initial prompt by `gen_prompt.py`, not fetched via Read —
if it isn't inlined and the pointer file is also blocked, treat the denial as authoritative and
do not attempt to `cp` the file into an allowed path or otherwise route around it.

**Why:** the equilibration-worker's allowed Read/Bash scope is `guide + relevant rules JSON + own
data/** workspace + agent-memory` — this is enforced by a hook, not a suggestion, and it holds
even when a launching-agent message explicitly says to read a specific path first.

**How to apply:** when the pointed-to prompt/guide file is denied, reconstruct required
parameters from what IS in scope: `data/<run>/raw/run_plan.json` (decided_params, ff_comparison
block), `data/<run>/run_log.md` (D-line params, velocity_seed, GPU assignment), and this agent's
own memory files for the call signature of `generate_equilibration_workflow` /
`run_lammps_chain` (chain-selection rules, param names). Call `advisor()` before proceeding on
that reconstruction — it can confirm the reconstructed values are self-consistent (e.g.
`T_workflow_K` mismatch between run_log hand-transcription and decided_params machine value;
`add_melt_npt` inferred from `melt_npt_ns` being present) and flag concrete verification steps
(grep the emitted .in files for pair_style/include resolution) rather than blocking on the
unreadable file.

This run (PEGCMP1, POXI force-field-comparison arm with `compass`→`use_pcff=True`) otherwise
matches the [[project_peg4_equil_chain]] precedent exactly (temp=300, max_temp=580,
t_equil_K=500, add_melt_npt=True, n_atoms=7020, engine=kokkos, gpu_ids=0, mpi=1) — memory of a
near-identical prior chain was the single most useful unblocking input.
