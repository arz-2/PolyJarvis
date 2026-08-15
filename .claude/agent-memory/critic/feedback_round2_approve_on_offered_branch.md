---
name: round2-approve-on-offered-branch
description: At critic_round 2, a planner taking either branch of a round-1 either/or finding is resolution — approve, replace the findings array (never append), and carry prose-only instructions forward as advisory lines
metadata:
  type: feedback
---

When round-1 findings were written as "either do X **or** state Y", the planner picking *either*
branch resolves the finding. Approve it.

**Why:** at `critic_round == 2` a retained finding means escalate/UNRESOLVED — the run stops. Killing
a run over the *shape* of an annotation the critic itself authorized is the boilerplate bounce
critic.md forbids. PSU1 (2026-08-13): all three round-1 findings were closed on offered branches —
`equil.success_criteria` gained the `require_glassy` companion set (binding_gates_pass +
`overall_pass_not_required` + `advisory_gates_non_blocking`), `equil_verdict:"PASS"` was *confirmed*
in D-05 evidence rather than replaced, and the Murnaghan dump suppression was *declared* to have no
tool arg rather than mechanized.

**How to apply:** on the round-2 Edit —

1. **Replace** `critique.findings`, do not append. `status:"approved"` sitting above the round-1
   revise strings is a self-contradicting artifact that the orchestrator and run_log both read.
   (PSU1 kept the old strings under a separate `superseded_round_1_findings` key.)
2. Edit the JSON with the `Edit` tool, never `json.load`/`json.dump` — the round-trip reformats a
   hand-formatted plan and has caused destructive reverts.
   **Exception when the array being replaced is long** (PLA1 round 2, 2026-08-14: 8 multi-sentence
   findings): `Edit` needs the *entire* old block reproduced byte-exactly, and retyping paragraph-length
   strings from a `cat -n` read is where a silent mismatch or truncation creeps in. Safe middle path —
   `readlines()`, locate the block by its own delimiters (`start` = the line equal to `  "critique": {`,
   `end` = the next line equal to `  },`), build the replacement with `json.dumps` on the NEW finding
   strings only, splice `lines[start:end+1]`, `writelines`. Every other byte of the plan is untouched,
   so this is not the forbidden whole-file round-trip. Verify after with
   `jq '.critique | {status, rounds, findings_count: (.findings|length)}'` plus a second `jq` on
   unrelated keys (`plan_mode`, `decided_params`, stage/decision counts) to prove nothing else moved.
3. Carry every instruction that still depends on a human/orchestrator action into an
   `"Advisory, no action required: ..."` line. The approval is its last visible carrier before
   execution.
4. Name the in-scope citation the approval actually rests on when the plan's own cite is to a file
   the critic cannot read — see [[critic-md-commands-blocked-use-read]].

Related: [[success-criteria-contradict-gating-path]], [[blocked-probe-is-not-a-plan-inconsistency]]
