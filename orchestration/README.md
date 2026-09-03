# Deterministic Control Plane

`orchestration/scripts/` contains executable workflow policy. The runtime does not read stage
guides or generate worker prompts.

| Component | Responsibility |
|---|---|
| `agent_api.py` | Public API that requires scientific planning before execution |
| `scientific_control.py` | Planning agent → deterministic script chain → conditional recovery |
| `run_campaign.py` | Resumable end-to-end campaign execution (the CLI accepts a plan, never an individual stage): build, the equilibration core ending at the gated melt hold, the cooling descent to `final_T_K`, thermal, mechanical, summary |
| `stage_params.py` | Plan and class configuration to concrete tool arguments |
| `protocol_policy.py` | Pressure-ladder selection and bounded recovery |
| `make_deterministic_plan.py` | Reproducible plan generation for configured classes: `run-plan` (run_plan.json) and `decision` (the fully-resolved decision.json the literature critic then critiques) |
| `validate_run_plan.py` | Structural and policy validation of plan artifacts |
| `enforce_gate.py` | Deterministic gate enforcement for both gated cells: `require_melt` on the melt hold (where `rg`/`ct` bind) and `require_glassy`/`require_rubbery` on the assessment cell |
| `hardware_runtime.py` | What this box has and who currently has it: live host/GPU probes (cores, nvidia-smi, host-fingerprint match) and the atomic GPU claim/release ledger: `status`, `claim`, `release`, `budget` |
| `select_hardware.py` | Hardware-policy resolution (D-08_hardware) and the GPU-hours cost model that prices it: `select`, `estimate`, `plan` |
| `forcefield.py` | Force-field admissibility resolution (D-01_ff) and everything it rests on: `select`, `capability`, `domain`, `provenance`, `emc-fields` |
| `select_system_size.py` | Fox-Flory DP floor resolution (D-04_system_size; entanglement Me for bulk_modulus is advisory context, not a floor); re-run live by `validate_run_plan.py` on every plan, not just hand-transcribed |
| `protocol_evidence.py` | The protocol evidence stores: schema, both ingest paths and retrieval — `ingest` (literature advisories), `ingest-internal` (completed validated runs), `query` (tiered: exact_smiles > exact_class > similar_class) |
| `rules_common.py` | `guides/polymer_rules.json` access, class/member resolution, and the RDKit canonicalization both rest on (`canon` CLI) — the most-imported module here |
| `rdkit_cli.py` | Every RDKit computation (canonicalization, Morgan/Tanimoto similarity, repeat-unit atom count and mass, group-contribution Tg estimate, backbone-path rigidity) as one CLI, run inside the RDKit-capable conda env via `mol_python.run_in_mol_env`; never imported directly |

Control events live in `data/<run>/raw/control_state.json`; execution state lives in
`data/<run>/workflow_state.json` (per-stage status/attempts) and each attempt's own
`data/<run>/attempts/<stage>/<attempt_id>/executor_state.json` (that attempt's resolved
parameters + computed outputs). Completed stages are skipped on resume. The recovery agent
is never called unless validation or a deterministic stage returns a structured issue.
