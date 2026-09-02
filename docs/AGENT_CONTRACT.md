# Agent Contract

PolyJarvis has two agent roles and one deterministic runtime.

## Scientific Planning Agent

The planning agent runs once at campaign start. Rather than authoring its decision file from
scratch, it starts from a `decision.json` **scaffold** that
`orchestration/scripts/make_deterministic_plan.py decision` deterministically pre-populates from the
polymer class's current defaults in `guides/polymer_rules.json` — one row per pre-simulation
policy in `orchestration/decision_policy.json` (`D-01_ff`, `D-02_charges`, `D-03_electrostatics`,
`D-04_system_size`, `D-08_hardware`), each carrying a `default_choice`, the policy's
`criteria_evaluated`, and any evidence already transcribable from the class entry. The agent's
job is to annotate that file in place: replace placeholder evidence with real, cited reasoning,
fill `rationale`/`assumptions`/`dominant_uncertainty`/`confidence`, and set `overrides` only
where it disagrees with a shown `default_choice`. It returns only scientific decisions:

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
