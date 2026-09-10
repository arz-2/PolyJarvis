# CRITICAL: the melt gate fails OPEN when nothing is measured

Found 2026-09-09 12:45 while checking sPVC_1.

## What happened

sPVC_1's equilibration was ACCEPTED (attempt-0006) and the run moved on to cooling. Its gate:

    "verdict": "PASS", "failing_binding_gates": [], "binding_gates": {}, "advisory_gates": {}

`binding_gates` is EMPTY. Nothing was evaluated. The melt was accepted for having no
measurements, not for passing anything. The run is now in cooling on an unverified melt, and the
gate that had failed it minutes earlier (msid_gaussian) was never re-checked.

## Chain of causation

1. The EXTEND remedy runs a restart-continuation of ONE stage into a NEW attempt directory, so
   `attempts/equilibration/attempt-0006/work/` contains only `npt_melt_hold`.
2. The chain observables (MSD, C(t)) are measured on `nvt_melt_hold.dump`, which that attempt
   never ran. stage_params resolved `melt_dump_path` to the LEGACY layout
   `data/sPVC_1/lammps/equil/nvt_melt_hold/nvt_melt_hold.dump` -- a path that does not exist in
   the attempts-based layout at all.
3. `check_equilibration_comprehensive.py` exited 1 with a traceback, so `equilibration.json` was
   written with only `density` and `gate` -- no `chain`, no `thermo`.
4. `collect_gates` reads those sections and returns None for every gate. None means "unmeasured"
   and `classify()` drops unmeasured gates from both dicts.
5. An empty binding set has no failing member, so the verdict is PASS.

Verified directly:

    classify({every gate: None}, "melt", 50, True)
      -> clause require_melt, binding_results {}, failing [] -> PASS

## The two defects

A. **enforce_gate fails open.** This is the safety inversion and the general fix. A binding
   clause with an EMPTY evaluated set must never return PASS. `require_melt` names the gates a
   melt must clear; if none of them could be evaluated, the correct verdict is a hard failure
   (or an explicit UNMEASURED verdict routed to recovery), never acceptance. Dropping an
   unmeasured gate is right per-gate and wrong for the whole set.

B. **An EXTEND attempt cannot be re-gated.** The extension re-runs one stage, but the gate needs
   observables from a stage it did not re-run. Either the gate must read the prior attempt's
   trajectory for stages the extension did not touch (the continuation appends, so the data is
   contiguous and on disk), or the extension must include the stages the gate reads.

## Blast radius

- sPVC_1 accepted an unverified melt and is in cooling. Must be stopped and re-gated.
- aPS_1 is ~12 minutes from finishing the identical 2 ns continuation and would be accepted the
  same vacuous way.
- Any prior run whose gate crashed would have passed the same way; worth auditing.
- PLLA_1 and iPMMA_1 are NOT affected: both gated on full chains with real measurements
  (PLLA_1 MSD/Rg2 2.902 with a populated binding set; iPMMA_1 failed on real numbers).

---

## Resolution (2026-09-09)

Three layers, landed in order. The primary defect was **not** the empty binding set — that was
the last line of a defence that had already been breached twice upstream.

### Layer 1 — a worker that reports failure in its RESULT must halt the caller

`run_campaign.wait_for_analysis` treated the run-level status as the only failure signal. But the
fourteen analysis workers in `mcp-servers/mcp-lammps-engine/server.py` do not raise when the CLI
script they shell out to exits non-zero — they `return {"status": "failed", "error": stderr}`.
That return value goes through `run_manager.complete()`, so the *run* is `"completed"` and only
the *result* dissents.

This is exactly why the two failures at the same call site were handled differently:

| Call | How the worker failed | Run status | Outcome |
|---|---|---|---|
| `extract_equilibrated_density` (02:58) | raised `TypeError` (missing `output_name` kwarg) | `failed` | `PROCESS_FAILED`, stage halted — **correct** |
| `check_equilibration_comprehensive` (11:59) | script exit 1, worker returned a dict | `completed` | failure dict read as data — **fail-open** |

New `_reject_failed_analysis()` raises `SystemExit` on a result whose own `status` is
`failed`/`error`, at the single point every analysis call already passes through. One fix, all
fourteen workers.

### Layer 1b — a partial result is not an adjudicable one

`_run_equilibration_gate` now refuses a comp missing the `thermo` or `chain` section. This catches
what an emptiness check structurally cannot: thermo present and passing, chain section absent →
`failing_binding_gates == []` → PASS on an unmeasured chain.

### Layer 2 — an empty binding set fails closed

`classify()` returns a fourth value, `unmeasured` — which of the gates the clause *names* produced
no value — and both `enforce()` and `enforce_live()` now map an empty `binding_results` to `FAIL`.

Scoped deliberately: a *single* `None` is still dropped, not failed. `finite_size` returns `None`
when the box or Rg could not be resolved and `msid` when `available: false`; those are calibrated
not-applicable states, and `test_finite_size_unavailable_is_dropped_not_failed` is a named
contract. `unmeasured_binding_gates` is reported in both payloads so a human and the recovery
agent can see *which* evidence is missing rather than inferring it from a bare FAIL. The
plain-require clause declares nothing missing — its binding set is whatever the run produced, so
it states no requirement that any given gate be measured.

### Defect B — the un-regatable continuation attempt

Root cause: `stage_params` fell through to the pre-v3 `data/<run>/lammps/equil/...` layout because
a continuation attempt runs one stage and so has no `nvt_melt_hold` entry to source the dump path
from. `CampaignStageExecutor.execute` now walks `prior_attempts` for
`stage_checkpoints["nvt_melt_hold"]` and carries the sibling dump forward — the same walk
`mechanical_resample_points` already uses.

This is the physically correct reading, not a convenience: extending the npt hold leaves the nvt
window untouched, so `chain_displacement` re-reads the same trajectory (sPVC_1: still 4.846×Rg²)
while `msid_gaussian` re-measures on the new npt window.

The `lammps_base` legacy fallback in `stage_params` is systemic and remains — noted, not fixed here.

### Regression tests

`tests/test_enforce_gate.py`: an all-None melt returns FAIL with `binding_gates == {}`;
`classify()` names its unmeasured gates; the plain clause declares none. Fixtures in
`tests/test_run_campaign.py` now emit both sections, since a single-section comp is a shape the
engine cannot produce.

---

## A third uncollected gate: per-component energy drift (found AND fixed 2026-09-09)

`_analyse_energy_components` tests bond/angle/dihedral/vdW/Coul/Kspace drift independently,
because a canceling drift hides inside the aggregate — bond energy still relaxing downward while
vdW drifts upward nets a flat TotEng while neither term has equilibrated. Its docstring cites
RadonPy's `check_eq` (`radonpy/sim/lammps.py`) gating components independently for the same reason.

It is computed, folded into `thermo["energy"]["equilibrated"]`, and printed in `d05_block.md`.
**No gate binds on it.** `collect_gates` reads `thermo.energy_drift`, which
`check_equilibration_comprehensive.py:1317` sets from `thermo["energy"]["drift"]` — the aggregate.
The component verdict is never flattened to the top level, so `enforce_gate` cannot see it.

Same defect class as `torsion`, which was computed from the day the script was written and only
collected on 2026-09-02. Two of the three gates that bound the melt clause as of this morning had
this history; the pattern is that a check gets written, reported in the markdown, and never wired.

Measured on the runs with a completed melt:

| run | aggregate TotEng | worst component | component verdict |
|---|---|---|---|
| sPVC_1  | 0.023% pass | vdw 0.237%  | pass |
| PLLA_1  | —           | dihedral 0.815% | pass |
| aPS_1   | 0.023% pass | **vdw 1.691%** | **FAIL** |
| iPMMA_1 attempt-0003 | — | **vdw 14.119%**, dihedral 1.720% | **FAIL** (the trapped 550 K melt) |

Round-1 predates the check — 0 of 36 archived campaigns carry `component_drift` — so there is no
archive calibration for a threshold, unlike the C(t) and MSID retirements.

### Resolution

`check_equilibration_comprehensive.py` now flattens the verdict to `thermo.energy_component_drift`
alongside the aggregate `energy_drift`; `enforce_gate.energy_component_drift_gate` reads it.

Binding at the MELT only, on the same reasoning that binds `rg` and `chain_displacement` there
and nowhere else: a melt is the state where every energy term CAN reach a stationary
distribution, so a term still relaxing is a real defect rather than the definition of the state.
Below Tg a glass ages indefinitely and its terms drift by construction, so binding it at the
assessment temperature would make the clause unsatisfiable -- the argument decision_policy.json
already makes for MSD. Advisory in `require_glassy` and `require_rubbery`.

It is in `EXTENDABLE_GATES`: a term still relaxing is the textbook case for buying more
trajectory, and a binding gate in neither the extendable nor the structural set falls through to
a hard FAIL. Absent (every result written before the flattening) reads None and is dropped.

`tests/test_all_gates_covers_every_key_collect_gates_emits` was added after the first version of
this change silently failed to bind: the test helper's `_ALL_GATES` list did not include the new
key, so every clause-membership assertion skipped it -- the same blind spot in the tests that the
missing flattening was in the code.

Consequence for the benchmark: **aPS_1 passes every OTHER binding gate but carries a 1.69% vdW
drift**, so its re-gate now routes to EXTEND rather than acceptance. sPVC_1 (worst term 0.246%)
and PLLA_1 (0.815%) clear the new gate. iPMMA_1's
figure is from the failed 550 K attempt and is consistent with the kinetic trap, not a separate
defect; its 600 K attempt-0004 is still running.

---

## msid_gaussian demoted to advisory (2026-09-09)

Retired from `BINDING_MELT` on measurement over the 36 round-1 campaigns. The full argument and
the three correlations are recorded in the source next to `BINDING_MELT`; the short version is
that `msid.slope` is a single power-law fit across two physically distinct regimes and tracks
chain stiffness rather than equilibration. All 9 archive failures are high; slope runs r = −0.66
against chain length and **r = +0.46 against displacement** — the wrong sign for a convergence gate.

aPS_1 confirmed the two-regime structure directly: combined 1.371 (fail), small-intermediate
1.573, **large_s 1.095 (pass)**, split at n=18.

The regime-split fields are NOT a drop-in replacement: `s_split` is a fixed fraction of chain
length (~max_n/3) where the crossover is a fixed physical length, and pairs-per-chain falls
linearly to 1 at n = max_n, so `large_s` is contaminated at its lower edge on short chains and
noise-dominated at its upper edge. The intended binding replacement is a block-convergence test on
MSID(n), mirroring `_torsion_js_stabilization`, which needs a block axis on `msid_accum`.

---

## A fourth defect: the extension length was a constant wearing a formula (fixed 2026-09-09)

Found while checking why aPS_1's first `energy_component_drift` EXTEND ran 10 ns.

`workflow_engine._continue_npt` sized any finding that carried no `extension_ns` like this:

```python
tau    = float(details.get("tau_ns")       or 0.5)
n_eff  = max(float(details.get("n_eff")    or 0), 1.0)
target = max(float(details.get("target_n_eff") or 20), n_eff)
ns = tau * target
```

**Nothing in this repository has ever written `tau_ns`, `n_eff` or `target_n_eff` into a
finding's details** — grep finds them only at these three read sites. So every path through this
returned exactly `0.5 * 20 = 10.0` ns, independent of the run, the stage and the gate. It reads
as a measurement-driven formula and is a hardcoded constant.

`_thermo_extension_ns`'s docstring says it *replaced* "a hardcoded `0.5 ns * 20`, which on aPS_1
would have bought 10 ns against a 2 ns stage -- 5x the entire melt hold, ~12 GPU-hours, from a
constant that had never seen the run." It did not replace it. It bypassed it for the gates listed
in the sizing sets and left it as the default for everything else.

### Two ways it fired

**Latent, then real (melt).** `energy_component_drift` was added to `EXTENDABLE_GATES` without a
matching entry in `EXTEND_ONE_MORE_WINDOW`, so `_thermo_extension_ns` returned None and aPS_1 was
handed 10 ns against a 2 ns melt hold. An unsized gate does not fail loudly — it silently buys a
whole stage.

**Live and unnoticed (cooling).** `do_cool_and_check`'s EXTEND emitted `relaxation_time_ns` but
never `extension_ns`, so EVERY cooling EXTEND took the constant. `npt_final` runs 500,000 steps =
0.5 ns, making that a **20x** overshoot. PLLA_1 and sPVC_1 were both in cooling when this was
found, one failing assessment gate away from it.

### Fix

  * `do_cool_and_check` now sizes its own EXTEND via `_thermo_extension_ns` against `npt_final`'s
    stage length. The cooling clause binds on the same thermo family as the melt, so the rule
    applies verbatim. This had to land FIRST -- removing the fallback without it would have left
    cooling with no remedy at all.
  * `energy_component_drift` added to `EXTEND_ONE_MORE_WINDOW`.
  * The fallback is replaced by a `ValueError` naming the failing gates. Both callers now size
    from measurement, so an unsized finding is a genuine gap, and declining routes it to the
    recovery agent with a cause -- the response the code already gave for `chain_displacement`,
    and what its own comment argued for: "A remedy that cannot size itself from a measured
    quantity must decline and say so, not guess."

### Tests

`test_every_extendable_gate_has_a_sizing_rule` (every member of `EXTENDABLE_GATES` is reachable
by `_displacement_extension_ns` or `_thermo_extension_ns`),
`test_an_unsized_continuation_declines_instead_of_inventing_a_length`, and
`test_no_default_extension_length_survives_anywhere_in_continue_npt` (a source-level guard
against `or 0.5` / `or 20` / `tau * target` returning).

### The general lesson

Three of the four defects recorded in this file are the same shape: **a value that is computed,
plumbed partway, and then read by nobody** — the crashed-analysis status, the per-component drift
verdict, the `tau_ns`/`target_n_eff` keys. The first two were checks that never reached the gate;
the third was a gate input nothing ever supplied. All three were invisible because the code path
around them ran without error. Before trusting a `.get(key) or default`, check whether anything
ever writes `key`.

---

## Defects 5-8: found by asking why sPVC_1's cooling looked different from PLLA_1's (2026-09-09)

The question was narrow — PLLA_1's cooling chain had 14 stages, sPVC_1's had one. Answering it
turned up four more defects, three of which were live on other campaigns at the time.

### 5. A continuation leaked across the stage boundary

`CampaignStageExecutor.execute` does `args = self.args`: **one mutable object shared by every
stage the process runs.** The equilibration-continuation block sets
`args.pending_continuation_path` under an explicit `stage == "equilibration"` guard, and nothing
clears it. `do_cool_and_check` reads it unconditionally (`run_campaign.py:1383`) and takes its
extend-only branch.

sPVC_1's three cooling attempts are what that looks like from outside. Line 70 of the deck:

```
read_restart .../attempts/equilibration/attempt-0003/work/npt_melt_hold/npt_melt_hold_out.restart
fix npt_fix all npt temp 300.0 300.0 100.0 iso 1.0 1.0 1000.0
run 1500000
```

The cooling stage read *equilibration's* restart and held at 300 K. Zero `cool_block`s: a 571 K
melt direct-quenched to the assessment temperature. The keys were already namespaced per stage
("separate keys, separate stage hash", says the comment) — the *path* they share was not.

**Fix:** reset every stage-scoped continuation/resume attribute at the top of `execute`, beside
the `engine_owned_recovery` reset that was already there.

### 6. `args.backbone_types`: read by one consumer, written by nobody

`do_cool_and_check` resolved `args.backbone_types or cls.get("backbone_types")`. The first is
read at exactly one line in the file and assigned at none. When a plan does not carry
`backbone_types` in `decided_params` (3 of the 4 live runs), both sides are `None`, and the
worker's first statement is

```python
bt_str = " ".join(str(t) for t in backbone_types)   # server.py:3061
```

`'NoneType' object is not iterable`, in **70 ms**, before the worker logged its own command line —
which is how it was identified: the launch log has a `Running comprehensive equilibration check:
python ...` line for the equilibration check and none for any of the three cooling checks. The
subprocess was never launched. Equilibration is unaffected because it derives the value locally
and passes it directly.

**Fix:** cool-check now uses the same `_resolve_backbone_types` derive-or-halt path equilibration
uses, and that helper reads the plan's persisted `derived_inputs` first — the only carrier that
survives both a process restart and a stage boundary (`cooling` depends on `equilibration` alone,
so `args.build_data_path` is never set for it).

A third, latent defect sits directly behind this one: `_resolve_cool_check_params`'s
`melt_dump_path` falls back to `data/<run>/lammps/cool/npt_final/npt_final.dump`, a flat
pre-attempt-layout path no run has ever written. It is the exact twin of the `npt_prod_log_path`
bug annotated three lines above it in the same function ("the bug that silently disabled this
binding gate on every run once") — the dump half was missed. It never threw only because defect 6
crashed first.

### 7. A remedy parameter re-invalidated its own stage on every fresh resume

`_reconcile_plan` computed `changed` as `effective_parameters` vs `decided_params`. A
remedy-introduced key lives **only** in the former — that is what the preservation logic added in
defect 4's fix exists to protect — so against `new` it compares unequal *forever*. Every
plan-hash change therefore re-invalidated whatever stage that key maps to.

The trap is silent until some process constructs a fresh engine. The melt gate's `derived_inputs`
write-back moved sPVC_1's plan hash at 11:59:08 while its engine was mid-run; the resume at 15:56
— for entirely unrelated reasons — recomputed `changed`, found `npt_continuation_ns` "changed",
and re-submitted a 2 ns melt continuation for an equilibration that had been **accepted for four
hours**. aPS_1 carried the same key and was one resume from the same thing.

**Fix:** snapshot the plan's own `decided_params` as `plan_decided_params` and diff against that,
so the comparison is plan-against-plan as its comment always claimed. `revise_plan` moves the
snapshot too, or the next hash change diffs a revised plan against the pre-revision baseline.

A related repair, not a code defect: PLLA_1's `effective_parameters` had never recorded
`backbone_types`, though the launch log shows its accepted equilibration ran with the plan's
`--backbone_types 1 2 3 6 7`. Any reconcile adds the key back, moving that stage's `input_hash`.
The stored hash was re-stamped after reproducing the old one byte-for-byte from the recorded
inputs — bookkeeping catching up with what ran, not a protocol change.

### 8. A reattaching resume could not claim the GPU its own chain was on

Detached chains survive an orchestrator restart, so a resume reattaches rather than resubmits.
But `gpu_claim` ran unconditionally, and `free_gpus()` filters on idleness — and that GPU is busy
**precisely because this run's own chain is on it**. So a reattach either landed on a different,
idle card (ledger naming a GPU doing nothing, silent about the loaded one) or, with nothing else
free, failed outright.

That second case is the one that matters: it is what stops a fix from reaching a live campaign.
With four runs on four GPUs and one free slot, the three orchestrators needing the defect-5 and -6
fixes could not all be restarted.

**Fix:** `hardware_runtime.py claim --adopt <ids>` records the claim on exactly the GPUs a
detached chain is already using, bypassing the idle check, and both reattach sites pass the ids
read from the chain script they are reattaching to. The ledger's job is to say where the work is.

### What this round adds to the lesson

Defect 4's write-up ended on "a value computed, plumbed partway, and then read by nobody." Defect
6 is another instance and defect 8 is its cousin (a real constraint the code declined to express).
But 5 and 7 are the mirror image, and worth naming separately: **a value that travels further than
its owner intended.** The continuation path outlived its stage; the remedy key outlived its
comparison. Both were introduced *by* correct-looking guards — `stage == "equilibration"` and the
preservation dict — that scoped the write and not the read.

The check that would have caught all four is the same one: for every value, name both ends. Who
writes it, and who reads it, and are those the same stage.
