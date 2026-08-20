# Deterministic Control Plane

`orchestration/scripts/` contains executable workflow policy. The runtime does not read stage
guides or generate worker prompts.

| Component | Responsibility |
|---|---|
| `agent_api.py` | Public API that requires scientific planning before execution |
| `scientific_control.py` | Planning agent → deterministic script chain → conditional recovery |
| `run_campaign.py` | Resumable single-stage or end-to-end campaign execution |
| `stage_params.py` | Plan and class configuration to concrete tool arguments |
| `protocol_policy.py` | Pressure-ladder selection and bounded recovery |
| `make_deterministic_plan.py` | Reproducible plan generation for configured classes |
| `validate_run_plan.py` | Structural and policy validation of plan artifacts |
| `enforce_gate.py` | Deterministic equilibration gate enforcement |
| `pick_gpu.py` | Atomic GPU claim and release ledger |
| `select_hardware.py` | Hardware-policy resolution (D-08_hardware) |
| `select_forcefield.py` | Force-field admissibility resolution (D-01_ff) |
| `select_system_size.py` | Fox-Flory/entanglement DP floor resolution (D-04_system_size); re-run live by `validate_run_plan.py` on every plan, not just hand-transcribed |
| `plan_system_size_arms.py` | Opt-in two-arm split when a run's tg and bulk_modulus DP floors diverge sharply — sizes each arm from its own property subset instead of the run-wide max |
| `merge_arm_summaries.py` | Combines two split arms' `run_summary.json` into one report |

Control events live in `data/<run>/raw/control_state.json`; execution state lives in
`data/<run>/workflow_state.json` (per-stage status/attempts) and each attempt's own
`data/<run>/attempts/<stage>/<attempt_id>/executor_state.json` (that attempt's resolved
parameters + computed outputs). Completed stages are skipped on resume. The recovery agent
is never called unless validation or a deterministic stage returns a structured issue.
