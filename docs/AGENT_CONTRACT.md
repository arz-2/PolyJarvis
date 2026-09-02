# Agent Contract

PolyJarvis has two agent roles and one deterministic runtime.

## Scientific Planning Agent

The planning agent runs once at campaign start. As of 2026-09-02 it does **not** author the
decision file at all: `orchestration/scripts/make_deterministic_plan.py decision --smiles ...`
writes a *complete* `decision.json`, resolving one row per pre-simulation policy in
`orchestration/decision_policy.json` (`D-01_ff`, `D-02_charges`, `D-03_electrostatics`,
`D-04_system_size`, `D-08_hardware`) from this repo's own resolvers — `solve_system_size`,
`select_hardware`, the `electrostatics_decision_guide`, and `polymer_rules.json`'s
`_metadata.primary_sources` citation records. Every criterion the policy names gets its own
evidence entry, tagged `origin: "autofill"`, including the criteria that layer cannot reach
(those say `NOT MEASURED` / `NOT ASSESSABLE` explicitly). `rationale` is written for it.

The agent's job is to **critique** that file, not fill it: the `literature-grounding-worker`
subagent returns an agree/disagree verdict per decision, and the calling session applies or
declines each `suggested_override`, transcribes any critic-backed sources with
`origin: "critic"`, and sets `confidence`. `confidence` comes back `"unreviewed"` (invalid) and
is the **only** remaining block on materialization — `--baseline` stamps `"low"` instead, for
the deterministic arm that runs with no LLM in the loop.

`default_choice` stays read-only provenance: `materialize_plan()` reads only
`criteria_evaluated`/`evidence`/`alternatives` off each row, so disagreement is expressed
through `overrides`. It returns only scientific decisions:

```json
{
  "polymer_class": "PSTR",
  "properties": ["density", "bulk_modulus"],
  "rationale": ["The requested 300 K state is glassy."],
  "overrides": {"npt_prod_ns": 8.0},
  "decision_evaluations": {
    "D-03_electrostatics": {
      "default_choice": "pppm",
      "criteria_evaluated": [
        "backbone_heteroatoms",
        "max_partial_charge",
        "computational_cost"
      ],
      "evidence": [{"claim": "PCFF electrostatics", "citation": "source"}],
      "alternatives": ["short-range treatment"]
    }
  },
  "assumptions": [],
  "dominant_uncertainty": "forcefield_transferability",
  "confidence": "medium"
}
```

`default_choice` is read-only provenance of what the class defaulted to — code never reads it
back out of `decision_evaluations` when materializing the plan, so editing it has no effect; a
disagreement is expressed through `overrides` instead. `D-05_convergence`,
`D-06_tg_fit_quality`, and `D-07_property_method` have no `decision_evaluations` row: each is
defined in `decision_policy.json` as a mechanized runtime gate verdict (`equil_verdict`,
`tg_gate_verdict`, `bm_gate_verdict`) to route on rather than a decision with a pre-simulation
default, and stay enforced solely through `planned_stages[*].success_criteria`.

The agent cannot set paths, commands, filenames, templates, or raw LAMMPS content. Code validates
every override and materializes the complete `run_plan.json`.

## Deterministic Chain

After planning, PolyJarvis launches these commands in order:

```text
validate_run_plan.py
run_campaign.py --stage build
run_campaign.py --stage equilibration
run_campaign.py --stage thermal       # only when Tg is requested
run_campaign.py --stage mechanical    # only when modulus is requested
run_campaign.py --stage summary
```

Each stage reads and writes structured state. A completed stage is skipped when the chain resumes.

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
