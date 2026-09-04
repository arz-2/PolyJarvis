# Agent Contract

PolyJarvis has two agent roles and one deterministic runtime.

## Scientific Planning Agent

The planning agent runs once at campaign start. As of 2026-09-02 it does **not** author the
plan at all, and as of 2026-09-04 there is no separate decision file for it to author:
`orchestration/scripts/make_deterministic_plan.py run-plan --smiles ...` writes a *complete*
`run_plan.json`. The file the agent critiques and the file that executes are the same file.

`decisions` holds exactly **one** row, `D-01_ff`. The others were retired because none was a
decision:

| retired row | why it was never a choice |
|---|---|
| `D-02_charges` | the charge scheme is the force field's own (`pcff` -> bond-increment, `opls` -> opls-library, `trappe` -> embedded, `gaff` -> RESP) |
| `D-03_electrostatics` | follows the same family (`lj_cut` iff `trappe`, otherwise `pppm`) |
| `D-08_hardware` | `hardware_policy.by_forcefield[family]`, a property of this host |
| `D-04_system_size` | a solver (`solve_system_size`), not a choice -- `overrides` cannot carry `dp_typical`/`nchain` |

All four were verified to be exact functions of the resolved field across all 21 classes before
retirement. They are now derived by `_derived_from_field()` **after** D-01 resolves, into
`decided_params` (charges, electrostatics), `hardware`, and `system_size`. That ordering is the
point: they used to be snapshotted from the class entry *before* the field was known and never
reconciled, so a SMILES resolving outside its class family recorded a charge scheme that
contradicted the field it built with.

`D-05_convergence`, `D-06_tg_fit_quality` and `D-07_property_method` still have no row: each is
defined in `decision_policy.json` as a mechanized runtime gate verdict (`equil_verdict`,
`tg_gate_verdict`, `bm_gate_verdict`) to route on rather than a decision with a pre-simulation
default, and stays enforced solely through `planned_stages[*].success_criteria`.

The agent's job is to **critique** the D-01 row, not fill it: the `literature-grounding-worker`
subagent returns an agree/disagree verdict on the force field, and the calling session applies
or declines its `suggested_override`, transcribes any critic-backed sources with
`origin: "critic"`, and sets `confidence`. `confidence` comes back `"unreviewed"` (invalid) and
is the **only** remaining block on materialization -- `--baseline` stamps `"low"` instead, for
the deterministic arm that runs with no LLM in the loop.

The row's `choice` stays read-only provenance: `materialize_plan()` reads only
`criteria_evaluated`/`evidence`/`alternatives` off it, so disagreement is expressed through
`overrides`.

```json
{
  "schema_version": "2.0",
  "plan_mode": "scaffold",
  "confidence": "unreviewed",
  "dominant_uncertainty": "protocol_transferability",
  "decisions": [
    {
      "id": "D-01_ff",
      "choice": "pcff",
      "admissible": ["pcff"],
      "criteria_evaluated": ["literature_support", "parameter_coverage",
                             "validation_data", "computational_cost"],
      "evidence": [{"claim": "...", "source_doi": "...", "origin": "autofill"}],
      "alternatives": ["gaff2"],
      "acknowledgements": {"ff_accuracy_prior_not_met": "..."},
      "critique": {"status": "pending_scientific_review", "rounds": 0, "findings": []}
    }
  ],
  "system_size": {"dp_typical": 30, "nchain": 10, "acknowledgements": {}},
  "hardware": {"engine": "kokkos", "mpi_ranks": 1, "gpu_per_run": 1, "ff_family": "pcff"},
  "overrides": {}
}
```

Two facts a plan MUST carry when it departs from its own evidence live on the record they
qualify, not in a plan-wide list: `ff_parameter_provenance` and `ff_accuracy_prior_not_met` in
`decisions[0].acknowledgements`, and `system_size_dp_floor` / `system_size_over_provisioned` in
`system_size.acknowledgements`. `validate_run_plan.py` reads them there.

`schema_version` is enforced: a plan written against an older schema is rejected structurally
rather than misread. It covers a different failure from `workflow_engine.ENGINE_VERSION` --
that one invalidates resumable *run state*, this one rejects a stale *plan file* before it
executes.

The agent cannot set paths, commands, filenames, templates, or raw LAMMPS content. Code
validates every override and materializes the complete `run_plan.json`.

## Deterministic Chain

After planning, PolyJarvis launches these commands in order:

```text
validate_run_plan.py
run_campaign.py --plan <run_plan.json>
```

`run_campaign.py` takes a plan, never an individual stage: which stages run is derived from
`plan["properties"]` by `track_registry`, and the engine walks them in order.

```text
build
equilibration   # ends at the gated melt hold
cooling         # only when a cell at final_T_K is needed (density, any modulus)
thermal         # only when Tg is requested
mechanical      # only when a modulus is requested
summary
```

Each stage reads and writes structured state. A completed stage is skipped when the chain resumes.

`equilibration` ends at a melt hold at `T_melt_hold_K` (per-SMILES:
`max(class T_equil_K, Tg + 200)`), gated there on the `require_melt` clause — the one place
chain relaxation is physically attainable, so `rg` and `ct` bind. `cooling` descends from that
same cell to `final_T_K` and carries the assessment gate. Both `thermal` and `cooling` start
from the melt hold independently; `mechanical` needs the assessment cell and so requires
`cooling`. A run asking only for `melt_density` stops after `equilibration`.

## Recovery Agent

The recovery agent receives a call only when validation or execution returns a structured issue.
It receives the intent, plan summary, issue code/detail, and attempt count. It may return:

```json
{
  "action": "retry",
  "rationale": "The failed process was transient.",
  "modifications": {}
}
```

Allowed actions are `retry`, `revise_plan`, and `stop`. Plan revisions use the same parameter
allowlist and bounds as initial planning. The runtime permits at most two recovery-agent calls.
