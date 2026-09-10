# recovery_r2 — recovery as completion, not diagnosis

Answers reviewer comment 3: *"Recovery should be defined as successful completion of the
intended simulation and property calculation, tested over repeated trials and preferably on
unseen failure cases. An end-to-end deterministic workflow baseline is still needed to
quantify the incremental contribution of the LLM."*

    python3 benchmarks/recovery_r2/injectors.py --verify  # prove each injector fires its code
    python3 benchmarks/recovery_r2/run_trials.py          # N trials x 2 arms, real ladder
    python3 benchmarks/recovery_r2/code_inventory.py      # which Finding codes can be minted
    python3 benchmarks/recovery_r2/fault_catalog.py       # the catalog, validated against that
    python3 benchmarks/recovery_r2/harvest.py             # score real campaign recoveries

## Two tiers, and the difference is the whole point

**Tier 1 — routing** (`injectors.py` + `run_trials.py`, zero GPU, seconds). Really corrupt a
real EMC cell, classify it through the exact validation call `run_campaign.py` makes, then
drive the **real `WorkflowEngine`** with the Finding that produced. Measures which remedy is
selected, how many applications the cap allows, whether it escalates, and where the arms
diverge. The executor is scripted, so completion here is scripted too.

**Tier 2 — completion** (needs GPU). The same injected cell through a real campaign, scored on
whether the stage reaches `accepted` and yields a gate-passing property value.

Reporting tier 1 as if it were tier 2 would repeat the exact error this benchmark exists to
correct — round 1 recorded `resolved: true` for runs whose `stages_completed` was `[]`.

## Tier 1 results

Control: the clean cell produces **no** validation error — without that, an injector that
"fires" is measuring the cell, not the injection. `params_file` is what makes the control
meaningful; without it every EMC cell reports five spurious "'Pair Coeffs' section missing".

| injector | target code | fires |
|---|---|---|
| `net_charge` — +0.9 e on one atom | `BUILD_CELL_INVALID` | ✓ |
| `truncate_atoms` — drop 3 rows, header over-counts (round-1 F6) | `BUILD_CELL_INVALID` | ✓ |
| `collapse_box` — zero the x dimension | `BUILD_CELL_INVALID` | ✓ |
| `undersized_cell` — demand a cutoff the box cannot honour | `SIZE_MIN_IMAGE_VIOLATION` | ✓ |

Driven through the real engine, 3 trials/arm, fault recurring 3× (every automatic cap is ≤ 2):

| injector / arm | status | automatic remedies | agent calls |
|---|---|---|---|
| `BUILD_CELL_INVALID` / **A1** | `escalation_required` ×3 | 0 | 0 |
| `BUILD_CELL_INVALID` / **A2** | `failed` ×3 | 0 | 1 |
| `SIZE_MIN_IMAGE_VIOLATION` / **A1** | `escalation_required` ×3 | 2 (`finite_size_rebuild`) | 0 |
| `SIZE_MIN_IMAGE_VIOLATION` / **A2** | `failed` ×3 | 2 (`finite_size_rebuild`) | 1 |

Three things this measures. `BUILD_CELL_INVALID` takes **zero** automatic remedies and goes
straight to escalation — correct, it is `agent_only`. `SIZE_MIN_IMAGE_VIOLATION` burns exactly
**2** applications of `finite_size_rebuild` and stops — the cap binding, observed rather than
assumed. And the arms are **distinguishable in the record**: A1 halts at `escalation_required`
(`no_recovery_agent_configured`), A2 spends an agent call first.

A2's stub returns `stop` rather than a repair, deliberately: the live campaign's own four agent
calls came back `stop`×3 / `revise_plan`×1, and a stub that always repaired would inflate A2
exactly where the ablation is trying to measure it.

## The definition

**Recovered** = the stage the finding fired on reaches `accepted` **and** the run yields a
gate-passing property value. Not "a remedy was applied", not "no more errors in the log", not
a correct diagnosis.

Round 1's own artifacts fail that definition, and that is the finding to disclose rather than
defend. `RECOV_F5_agent.json` and `RECOV_F6_agent.json` record `"resolved": true` with
`stages_completed: []` and `terminal_state: "unknown"`, while the matching run logs say
outright *"Rebuild + equilibration not executed (task scope = diagnose + decide)."* The
reviewer read the benchmark correctly.

## The gap this fills

Round 1 had a **repeatable fault catalog driving an architecture that no longer exists** —
those transcripts capture a `molecule-builder` subagent, and v2's `.claude/agents/` holds only
`literature-grounding-worker.md`. v2 has a **live, enforced ladder with no fault test** —
`default_remedies()`, per-code caps, `MAX_AUTOMATIC_REMEDIES=12`, `MAX_AGENT_DECISIONS=2` —
and no fault-injection code anywhere (`grep inject/fault_catalog/F1_`: zero hits).

Each half is missing the other's. This supplies v2's missing half.

## Design surface: 27 of 42 routed codes are real

`default_remedies()` routes 42 codes; **15 have no producer**. A fault designed around one
fires nothing and silently measures nothing. `code_inventory.py` derives the split by reading
`tests/test_recovery_code_inventory.py`'s map rather than keeping a second copy that can rot,
and `fault_catalog.validate()` refuses any fault outside the live set.

That check earned its place immediately: the first draft of this design targeted
**`EQUIL_DRIFT`**, which has no producer. The code the equilibration gate actually mints is
`EXTEND`.

## R1 — the free half, already producing results

The live stereo_r2 pilot has generated real remedy events on **unplanned** failures — the
strictest reading of "unseen failure cases", since nobody chose them. One is a genuine harness
bug caught in flight (`_run_extract_equilibrated_density() got an unexpected keyword argument
'output_name'`).

`harvest.py` scores each against the definition above, reading `remedy_history[]` for the
event log and `stages.<stage>.status` for the outcome. Stages still in flight score `PENDING`
and are **excluded from the denominator**, not counted as either outcome. `PEG1_gate_validation`
is not a stereo_r2 run and is reported separately rather than pooled.

### The accounting rule that keeps it honest

Escalations are read from **both** `agent_escalations` and
`agent_escalations_retired_by_operator`. Operators retired PLLA_1's and aPS_1's escalations
on 2026-09-09 (causes that "no longer exist": an external kill, the since-retired ct gate, and
a code defect in the EXTEND continuation path). Both runs now report `agent_escalations: 0`
having actually spent two each, so the live counter alone under-reports what the campaign cost
in autonomy terms. `operator_interventions` is reported
alongside and never omitted — an undisclosed manual rescue inside a campaign whose headline
claim is autonomous execution is precisely what this reviewer comment is about.

## R2/R3 — the catalog

Six faults, every one keyed to a live code. Two rules:

**Inject at the gate, not the physics.** Tightening a threshold so a healthy trajectory fails
it exercises the identical remedy path for minutes of GPU instead of hours. Every fault in the
catalog is gate-level or a replay; none needs real MD to fail.

**Score by completion.** See the definition above.

| id | code | remedy | stage | cost |
|---|---|---|---|---|
| V1 | `BUILD_CELL_INVALID` | **agent_only** | build | seconds |
| V2 | `MINIMIZE_NOT_CONVERGED` | `raise_minimize_tolerance` | equilibration | minutes |
| V3 | `EXTEND` | `continue_npt` | equilibration | one continuation |
| V4 | `SIZE_MIN_IMAGE_VIOLATION` | `finite_size_rebuild` | build | build only |
| V5 | `TG_REVIEW` | `tg_breakpoint` | thermal | thermal replay |
| V6 | `BM_INADMISSIBLE_NONMONOTONIC` | `murnaghan_resample` | mechanical | ~0 (replay) |

**V1 is R3's trigger** — but R3 is no longer starting from zero. The campaign has already
spent four recovery-agent calls, and their decisions are preserved in
`agent_escalations_retired_by_operator`: **3 `stop`, 1 `revise_plan`, 0 `retry`**. `harvest.py`
extracts them. V1's job is to add *controlled, repeatable* trials to that organic sample, not
to produce the first observation.

Two caveats are recorded in the catalog rather than discovered later. `continue_npt` now
*refuses* rather than guesses when no measured quantity is available to size an extension
(added after a mis-sized fallback nearly requested 17 453 ns), so a fault that removes the
measurement tests the refusal, not the extension. And because all 21 classes sit at exactly
1.00× `tg_min_steps_per_T`, `tg_breakpoint`'s halving of `tg_t_step_K` drops the sweep under
its own floor and the remedy declines — **that remedy may be unreachable in practice**, which
is itself worth measuring.

## R4 — the ablation, run faulted

| Arm | What | LLM |
|---|---|---|
| A0 stock | EMC's own FF routing + generic numerics, `polymer_rules.json` not consulted | none |
| A1 deterministic | `run_graph.py --no-llm`; automatic ladder only, escalation terminal | none |
| A2 full | critic + adjudicator + the 2-call recovery agent | yes |

**Run faulted, not clean.** On a clean PE campaign A1 and A2 would almost certainly return the
same number — the pilot shows the automatic ladder resolving every finding without the agent,
so the measured LLM contribution would be zero, not because the LLM is worthless but because
nothing in a clean run reaches it. The `agent_only` faults are the discriminating rows: A1 must
halt on `escalation_required` where A2 may complete, and that difference *is* the incremental
contribution. A0 runs clean only — it has no recovery, so faulting it measures nothing.

If the clean arms do come out A1 ≈ A2, **report it**: "the deterministic core carries this
system unaided" is a legitimate finding, but it must be stated, not left as an unexplained null.

PE is the system: cheapest at 2.25 GPU-h priced, and unlaunched, so R4 neither disturbs nor
waits on the four in-flight pilot runs.

## The blocking defect this fixed

`nodes.execute()` passed `--recovery-agent-command` **unconditionally**. `no_llm` reached
`critique()` and `adjudicate()` but never `workflow_engine`, `scientific_control` or
`agent_api` — zero grep hits. So the "deterministic arm" still consulted a model up to twice on
any escalation, and any incremental-contribution number measured with it would have understated
the LLM by exactly what the recovery agent supplied.

Fixed 2026-09-09; `tests/test_langgraph_no_llm_arm.py` is the regression, and it asserts both
directions — the LLM arm must *keep* its recovery agent, since suppressing recovery everywhere
would measure nothing at all. `workflow_engine._escalate` already had the `None` branch,
returning `escalation_required` with `reason="no_recovery_agent_configured"`, distinguishable
in the record from a spent cap (`"max_agent_decisions_reached"`) — so the harvest can tell
*this arm had no agent* from *the agent ran out*.

## Status

| | |
|---|---|
| R1 harvest | **running**, grows with the campaign |
| Code inventory + catalog validation | **working**, negative-tested |
| `--no-llm` really LLM-free | **fixed + regression-tested** |
| R2/R3 injectors | designed, not written |
| A0 stock planner | designed, not ported |

## What was deliberately not ported

`fault_catalog.NOT_PORTED` carries the reasons. In short: F1/F2 surface as generic
`PROCESS_FAILED` and measure nothing specific; F3 is superseded by V5; F4's v2 code path is
unverified, so V1 is the reliable `agent_only` trigger; and `error_classifier.py` keys off
round-1 `recover.md` line numbers that no longer exist. The `RECOV_F5/F6_AGENT` transcripts are
cited as the disclosed round-1 limitation — they cannot be replayed against v2 and should not be.
