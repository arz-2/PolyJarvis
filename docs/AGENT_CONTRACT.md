# Agent Contract

PolyJarvis has two agent roles and one deterministic runtime.

## Scientific Planning Agent

The planning agent runs once at campaign start. It receives the user intent, configured polymer
classes, the allowed parameter override keys, and the evaluation criteria from
`orchestration/decision_policy.json`. It returns only scientific decisions:

```json
{
  "polymer_class": "PSTR",
  "properties": ["density", "bulk_modulus"],
  "rationale": ["The requested 300 K state is glassy."],
  "overrides": {"npt_prod_ns": 8.0},
  "decision_evaluations": {
    "D-03_electrostatics": {
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
