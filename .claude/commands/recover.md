---
description: Diagnose and plan recovery for a failed PolyJarvis simulation stage
allowed-tools: Read, Bash(find:*), Bash(grep:*), Bash(ls:*), Bash(ps:*), Bash(cat:*), Bash(tail:*), Bash(head:*), Bash(wc:*), Bash(jq:*)
---

Source of truth for headless `/recover` diagnosis, invoked by
`orchestration/scripts/recovery_agent_cli.py` — itself called from `WorkflowEngine._escalate`
(inner ladder, `orchestration/scripts/workflow_engine.py`) and `ScientificControlPlane`'s outer
loop (`orchestration/scripts/scientific_control.py`). **You recommend, you never apply.** You
never write, edit, resubmit, or claim/release any resource yourself — but you may decide
`action: retry` or `revise_plan` (with concrete `modifications`), not just `stop`. The calling
engine re-validates and applies whatever you return through its own bounded machinery (forbidden
overrides rejected, `plan_validator`/`_validate_overrides`/`_validate_protocol_relationships`
re-checked, capped at `MAX_AGENT_DECISIONS`/`MAX_RECOVERY_ATTEMPTS`=2 escalations per run).

You are reached only when the automatic ladder below could **not** resolve the failure itself:
either the `Finding.code` has no registered remedy (`agent_only`), or its per-route cap
(`Remedy.local_cap`) is already exhausted. Most failures never get here — say so plainly if the
`remedy_history` you read shows the engine already tried the right thing and simply ran out of
attempts, rather than re-deriving a fix it already attempted.

## 1. Orient on the run

You're given `run_name`, `track`, `step`, `symptom` (a JSON blob — `code`, `detail`, `severity`,
`recovery_history`). Read the durable state directly, not a log transcript:

```bash
cat data/<run_name>/workflow_state.json
```

Key fields: `active_finding` (the blocking code that stopped it), `remedy_history` (every
auto-remedy already applied, with `remedy_id` and `application` number — so you know which rungs
of a capped ladder are spent), `agent_escalations` (prior calls to you this run, if any —
`MAX_AGENT_DECISIONS=2` per workflow, `MAX_RECOVERY_ATTEMPTS=2` in the outer loop). Cross-check
`stages.<stage>.attempts[-1].manifest` for the failing attempt's own `findings`/`outputs`.

## 2. What auto-remedied and what didn't

`workflow_engine.py`'s `default_remedies()` is the authoritative registry — read it directly for
exact formulas/caps rather than trusting this table to stay current. Summary, by track:

| Track | Blocking code | Auto-remedy (capped) | If it reaches you |
|---|---|---|---|
| Foundation | `SIZE_MIN_IMAGE_VIOLATION`, `SIZE_CHAIN_SELF_IMAGE`, `FINITE_SIZE_FAILED` | `finite_size_rebuild` — larger `nchain`, ×2 | Structural; only escalates if the rebuilt cell still fails |
| Foundation | `UNSAFE_HARDWARE_PIN` | `safe_hardware`, ×1 | Policy has no safe hardware recommendation — needs a human call |
| Foundation | `UNIMPLEMENTED_PARAMETER`, `OVERRIDDEN_NOOP_PARAMETER` | `remove_noop`, ×1 | — |
| Foundation | `FORCE_FIELD_TYPING_FAILED` | `unique_forcefield`, ×1 (only if exactly one alternative) | `FORCE_FIELD_TYPING_AMBIGUOUS` (>1 alternative) is `agent_only` — pick one, cite the evidence |
| Foundation | `EQUIL_DRIFT`/`EQUIL_SEM`/`EQUIL_N_EFF`/`EXTEND` | `continue_npt`, ×2 — extension length from measured τ_relax | **Price it first (§3)** — a Class B gate whose gap is actually bias (not variance) is the wrong lever |
| Foundation | `UNDER_ANNEALED_COOLING` | `slower_cooling` — doubles `npt_cool_steps`/attempt, ×2 | Quench-rate trapping only; do not conflate with melt-stage deficits |
| Foundation | `MELT_STAGE_DEFICIT` | `melt_hold`, ×2 — attempt 1 doubles `eq_annealing_cycles` (more thermal-cycling depth to escape a bad initial pack); attempt 2 keeps that and adds a bounded 5 ns isothermal melt hold (deliberately short of the ~100 ns full-convergence literature value — PolyJarvis surveys, it doesn't optimize a single polymer) | Both rungs tried and density still low → likely genuine FF underbinding, not annealing depth; don't recommend a longer hold, escalate instead |
| Foundation | `HOMOG_HETEROGENEOUS`/`DENSITY_HETEROGENEITY` | `melt_homogeneity`, ×2 | Melt-only signal — don't apply to a glassy 300K read |
| Thermal | `TG_NOT_REPORTABLE` | `tg_sampling` — doubles `tg_steps_per_t`, then halves `tg_t_step_K` (floor 5K), ×7 | Fit genuinely won't resolve at any floor-respecting rate |
| Thermal | `TG_REVIEW` | `tg_breakpoint` — halves `tg_t_step_K` once, ×1 | primary/alt Tg gap >20K persists — check whether the class needs `tg_slope_gate_fallback=slowest_rate` |
| Mechanical | `BM_FALLBACK_DEFORM` | `deformation_fallback`, ×1 | — |
| Mechanical | `BM_INADMISSIBLE_NONMONOTONIC` | `murnaghan_resample`, ×1 | — |
| Mechanical | `BM_INADMISSIBLE` | `conditional_deformation`, ×1, glassy only | Rubbery + inadmissible has no auto-fallback — `agent_only` |
| Mechanical | `DEFORM_NEGATIVE_MODULUS` | `negative_deformation` — switches to the slow-rate leg, halves strain max, ×1 | — |
| Mechanical | `DEFORM_RATE_SENSITIVE` | `rate_sensitivity` — lowers the slow-leg rate toward a floor, ×1 | `DEFORM_RATE_SENSITIVITY_PERSISTS` after that is `agent_only` |
| Mechanical | `DEFORM_ANISOTROPIC`, `DEFORM_INADMISSIBLE` | none | `agent_only` — single-axis K is a biased estimator here; no lever fixes it, needs a different deform direction or a human call |
| Cross-cutting | `PLAN_VALIDATION_FAILED`, `PLAN_AGENT_CONTRACT_ERROR`, `ARTIFACT_INTEGRITY_FAILED`, `UNEXPLAINED_STAGE_FAILURE`, `REMEDY_EXHAUSTED`, `AUTOMATIC_REMEDY_CAP_REACHED` | none | Always `agent_only` by design |
| Any | `PROCESS_FAILED`/`PROCESS_DEAD_NO_SENTINEL`/`PROCESS_TIMEOUT`/`*_PROCESS_FAILED` | `transient_retry`, unchanged params, ×2 | Look for a real cause (disk, GPU claim, host) before recommending a third blind retry |

A `Finding` with `confidence="low"` never auto-remedies even if a route exists (routes straight
here) — check whether that's warranted or whether the emitting check should have scored higher
confidence.

## 3. Price the rung

Mandatory before recommending anything that trades wall time for a property value (another
EXTEND, a slower Tg rate, more annealing cycles beyond what `melt_hold` already tried). Skip only
for Class A structural remedies (`finite_size_rebuild` and friends).

```bash
python3 orchestration/scripts/remedy_economics.py \
  --failing-gate <gate> --gate-class <A|B|C|D> \
  --lever <cooling_rate_K_per_ns|trajectory_ns|nchain|eq_annealing_cycles> --lever-direction <lower|higher> \
  --history "<lever>:<metric>,..." --next-lever <value> \
  --target-floor <gate threshold> --physical-target <experimental value, not the band edge> \
  --sem <metric SEM> --last-rung-hours <wall time of the most recent rung> \
  --cost-exponent <-1 for cooling rate, +1 for trajectory length>
```

`--history` comes from `remedy_history` in `workflow_state.json` (one lever:metric pair per rung
already spent). Route on the verdict — transcribe it and its `reason` verbatim, never re-derive
the arithmetic:

| Verdict | Action |
|---|---|
| `SPEND` | Recommend the rung. `spend_limit: one rung` means the slope isn't measured yet — one rung, then re-run this check |
| `SPEND_STRUCTURAL` | Class A — recommend the structural remedy; economics tests don't apply |
| `STOP_ANNOTATE` | `verdict: accept_with_annotation` — spend no further rung, carry `annotation_required` forward |
| `WRONG_LEVER` | This remedy can't address this gate — re-diagnose, don't spend the rung |
| `PRECONDITION_UNMET` | Supply the named argument and re-run; never guess it |

Thresholds live in `decision_policy.json`'s `policies.equilibration.remedy_economics` — the script
reads them; this file doesn't restate them.

## 4. Required output

Return exactly one JSON object matching `recovery_agent_cli.py`'s schema — no free text:

```json
{"action": "retry | revise_plan | stop",
 "modifications": {"decided_params key": "value, ... — only when action is revise_plan, else {}"},
 "rationale": "root cause and why this action, citing the workflow_state.json evidence or remedy_economics verdict"}
```

Choose `revise_plan` only when you're confident of both the root cause and the fix, and the
modification is a single, well-evidenced `decided_params` override — e.g. `FORCE_FIELD_TYPING_
AMBIGUOUS` → `{"preferred_ff": "<the alternative you picked>"}`. Choose `retry` only when you've
confirmed the cause was transient (stale process, disk, GPU claim) and is now resolved — never as
a third blind attempt. Choose `stop` for anything genuinely novel or ambiguous, or any row above
marked `agent_only` with no clear single fix (`UNSAFE_HARDWARE_PIN`, `DEFORM_ANISOTROPIC`/
`DEFORM_INADMISSIBLE`, the cross-cutting rows). The engine re-validates `modifications` against
its own parameter whitelist and rejects unsafe keys regardless of what you send.

## Session reattach

The run is resumable by construction — `WorkflowEngine` reloads `workflow_state.json` on
construction and skips every `accepted` stage. If the driving Claude session died mid-run, there
is no special reattachment procedure: re-invoke the same command
(`scientific_control.py`/`run_campaign.py --plan data/<run_name>/raw/run_plan.json`) and it
resumes from the last accepted stage. Check `ps aux | grep run_campaign` first in case the
original process is still alive.
