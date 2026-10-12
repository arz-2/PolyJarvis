# Recovery benchmark — report

Status as of 2026-09-09. Answers reviewer comment 3. Reproduce every number below with
`harvest.py`, `code_inventory.py` and `fault_catalog.py`; `harvest.json` is the machine-readable
form. The campaign is live, so R1's figures grow.

---

## 1. The definition, and why round 1 failed it

**Recovered** = the stage the finding fired on reaches `accepted` **and** the run yields a
gate-passing property value. Not "a remedy was applied". Not "no more errors in the log". Not a
correct diagnosis.

Round 1's own artifacts fail this, and it is better to disclose that than defend it:
`RECOV_F5_agent.json` and `RECOV_F6_agent.json` record `"resolved": true` with
`stages_completed: []` and `terminal_state: "unknown"`, while the matching run logs state
*"Rebuild + equilibration not executed (task scope = diagnose + decide)."* The reviewer read the
benchmark correctly.

## 2. The structural gap

| | Fault catalog | Live architecture |
|---|---|---|
| Round 1 | **yes** — F1–F6, real captured aborts | **no** — the `molecule-builder` subagent those transcripts capture no longer exists; v2's `.claude/agents/` holds only `literature-grounding-worker.md` |
| v2 | **no** — `grep inject/fault_catalog/F1_` returns zero hits | **yes** — `default_remedies()`, per-code caps, `MAX_AUTOMATIC_REMEDIES=12`, `MAX_AGENT_DECISIONS=2` |

Each half is missing the other's. This benchmark supplies v2's, keyed to v2's own `Finding`
codes rather than round-1 `recover.md` line numbers.

## 3. Design surface — 27 of 42 routed codes are real

    42 routed codes: 16 live automatic, 11 live agent-only, 15 unreachable

Fifteen codes have no producer, so a fault built on one fires nothing and silently measures
nothing. `fault_catalog.validate()` refuses them. It caught this design's own first draft, which
targeted **`EQUIL_DRIFT`** — no producer; the code the equilibration gate actually mints is
`EXTEND`. `EQUIL_SEM` and `EQUIL_N_EFF` are the same trap.

## 4. R1 — what the live campaign has already produced

Unplanned failures from production runs: the strictest reading of "unseen failure cases",
since nobody chose them.

**Completion rate, reviewer's definition: 3 / 3 scored = 100%**, with **8 events still in
flight excluded from the denominator** rather than counted as successes. Eleven events total.

| Remedy | recovered | pending |
|---|---|---|
| `transient_retry` | 2 | 6 |
| `continue_npt` | 1 | 2 |

Codes seen so far: `PROCESS_FAILED` (8), `EXTEND` (3). The ladder has not yet been exercised
beyond two of its sixteen automatic routes — which is the honest limit of what R1 alone can
claim, and the reason R2 exists.

### Autonomy cost — the number the live counter hides

    agent escalations:        4   (4 retired by an operator)
    operator interventions:   4
    recovery-agent decisions: {stop: 3, revise_plan: 1}   (1 carried an actual plan change)

`PLLA_1` and `aPS_1` both report `agent_escalations: 0` today having actually **spent two
each**. An operator archived them into `agent_escalations_retired_by_operator` on grounds that
the causes "no longer exist". Reading only the live counter under-reports what the campaign
cost in autonomy terms, so `harvest.py` reads both lists and reports the sum.

The four manual interventions must be disclosed for the same reason: a campaign whose headline
claim is autonomous execution cannot quietly contain hand-rescues.

### What the agent actually decided

| Run | When | Action | Modification |
|---|---|---|---|
| PLLA_1 | 09-08 23:39 | `stop` | — |
| PLLA_1 | 09-09 12:24 | **`revise_plan`** | `nvt_melt_min_steps: 15_000_000` |
| aPS_1 | 09-08 23:39 | `stop` | — |
| aPS_1 | 09-09 14:21 | `stop` | — |

**The most interesting result in this report.** All three `stop` rationales conclude the root
cause lay *outside the recovery contract*: a host-level kill with healthy physics at death; an
environmental failure; and a code defect in the EXTEND continuation path that "no key in the
override contract reaches". The agent diagnosed correctly each time and correctly declined to
invent a plan-level fix for a harness problem.

The single `revise_plan` is a real scientific correction: C(t) on the 5 ns melt had decayed only
11.5%, so the melt was not chain-relaxed, and the agent raised `nvt_melt_min_steps` to 15 M.

That distribution — 3 stop / 1 revise_plan / 0 retry — reframes the reviewer's question. On this
evidence the ceiling on autonomous recovery is not the agent's reasoning; it is that most
failures encountered so far were harness defects, which no plan-level lever can reach.

## 5. R2/R3 — the controlled catalog

Six faults, every one validated against the live-code set. Two rules: **inject at the gate, not
the physics** (a tightened threshold exercises the identical remedy path for minutes instead of
hours — every fault below is gate-level or a replay), and **score by completion**.

| id | code | remedy | stage | cost |
|---|---|---|---|---|
| V1 | `BUILD_CELL_INVALID` | **agent_only** | build | seconds |
| V2 | `MINIMIZE_NOT_CONVERGED` | `raise_minimize_tolerance` | equilibration | minutes |
| V3 | `EXTEND` | `continue_npt` | equilibration | one continuation |
| V4 | `SIZE_MIN_IMAGE_VIOLATION` | `finite_size_rebuild` | build | build only |
| V5 | `TG_REVIEW` | `tg_breakpoint` | thermal | thermal replay |
| V6 | `BM_INADMISSIBLE_NONMONOTONIC` | `murnaghan_resample` | mechanical | ~0 (replay) |

N=3 trials each, so the output is a rate rather than an anecdote. V1 is R3's trigger — it
reaches the agent path for build-only compute, adding controlled repeatable trials to the
organic sample in §4.

Two caveats recorded up front rather than discovered later:

- `continue_npt` now **refuses** rather than guesses when no measured quantity can size an
  extension. A fault that removes the measurement tests the refusal, not the extension.
- All 21 classes sit at exactly 1.00× `tg_min_steps_per_T`, so `tg_breakpoint`'s halving of
  `tg_t_step_K` drops the sweep under its own floor and the remedy declines. **That remedy may
  be unreachable in practice** — itself a result worth reporting.

## 6. R4 — the ablation, and the defect that would have invalidated it

| Arm | What | LLM |
|---|---|---|
| A0 stock | EMC's own FF routing + generic numerics, `polymer_rules.json` not consulted | none |
| A1 deterministic | `run_graph.py --no-llm`, automatic ladder only, escalation terminal | none |
| A2 full | critic + adjudicator + the 2-call recovery agent | yes |

**`--no-llm` was not LLM-free.** `nodes.execute()` passed `--recovery-agent-command`
unconditionally; `no_llm` reached `critique()` and `adjudicate()` but never `workflow_engine`,
`scientific_control` or `agent_api`. The "deterministic arm" still consulted a model up to twice
on any escalation, so any incremental-contribution number measured with it would have
understated the LLM by exactly what the recovery agent supplied. Fixed 2026-09-09;
`tests/test_langgraph_no_llm_arm.py` asserts both directions, since suppressing recovery in
*both* arms would measure nothing at all. The engine already distinguished
`no_recovery_agent_configured` from `max_agent_decisions_reached`, so the harvest can tell *this
arm had no agent* from *the agent ran out*.

**Run the arms faulted, not clean.** On a clean PE campaign A1 and A2 would very likely return
the same number — §4 shows the automatic ladder resolving everything it was handed without the
agent — so the measured contribution would be zero, not because the LLM is worthless but because
nothing in a clean run reaches it. The `agent_only` faults are the discriminating rows: A1 must
halt on `escalation_required` where A2 may complete. If the clean arms do come out A1 ≈ A2,
report it — "the deterministic core carries this system unaided" is a legitimate finding, but it
has to be stated, not left as an unexplained null.

System: **PE** — cheapest at 2.25 GPU-h priced, and unlaunched, so it neither disturbs nor waits
on the four in-flight pilot runs. ~20 GPU-h.

## 7. Status

| Component | State |
|---|---|
| R1 harvest | **running**, results in §4, grows with the campaign |
| Code inventory + catalog validation | **working**, negative-tested on all four failure modes |
| `--no-llm` genuinely LLM-free | **fixed + regression-tested** (1789 pass, 0 fail) |
| R2/R3 injectors | designed, not written |
| A0 stock planner | designed, not ported from `1a6ca54` |

## 8. What this cannot yet claim

- The completion rate rests on **3 scored events across 2 remedy routes**. It is a real number
  under the reviewer's definition, not a sufficient one.
- Fourteen of the sixteen automatic routes have never fired in production. R2 is what exercises
  them.
- No arm comparison exists yet, so the LLM's incremental contribution is still unquantified.
- `tg_breakpoint` may be structurally unreachable (§5) — suspected, not yet measured.
