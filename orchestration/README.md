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
| `make_deterministic_plan.py` | Reproducible plan generation for configured classes: `run-plan` writes the complete `run_plan.json` the literature critic then critiques. The separate `decision` subcommand and its decision.json were folded into the plan on 2026-09-04 |
| `validate_run_plan.py` | Structural and policy validation of plan artifacts |
| `enforce_gate.py` | Deterministic gate enforcement for both gated cells: `require_melt` on the melt hold (where `rg`/`ct` bind) and `require_glassy`/`require_rubbery` on the assessment cell |
| `hardware_runtime.py` | What this box has and who currently has it: live host/GPU probes (cores, nvidia-smi, host-fingerprint match) and the atomic GPU claim/release ledger: `status`, `claim`, `release`, `budget` |
| `select_hardware.py` | Hardware-policy resolution (D-08_hardware) and the GPU-hours cost model that prices it: `select`, `estimate`, `plan` |
| `forcefield.py` | Force-field admissibility resolution (D-01_ff) and everything it rests on: `select`, `capability`, `domain`, `provenance`, `emc-fields` |
| `select_system_size.py` | Fox-Flory DP floor resolution (D-04_system_size; entanglement Me for bulk_modulus is advisory context, not a floor); re-run live by `validate_run_plan.py` on every plan, not just hand-transcribed |
| `protocol_evidence.py` | The protocol evidence store: schema, both ingest paths and retrieval — `ingest` (literature advisories), `ingest-internal` (completed validated runs), `query` (tiered: exact_smiles > exact_class > similar_class) |
| `rules_common.py` | `guides/polymer_rules.json` access, class/member resolution, and the RDKit canonicalization both rest on (`canon` CLI) — the most-imported module here |
| `rdkit_cli.py` | Every RDKit computation (canonicalization, Morgan/Tanimoto similarity, repeat-unit atom count and mass, group-contribution Tg estimate, backbone-path rigidity, build-blocker moiety screen, polymer classification) as one CLI, run inside the RDKit-capable conda env via `mol_python.run_in_mol_env`; never imported directly. Its `classify` subcommand additionally needs RadonPy, so it runs in `mol-builder` rather than `radonpy` |
| `classify_cli.py` | `polymer_class` and the full chemical-group profile of a repeat unit — the step a live session used to do by hand. Calls RadonPy's `poly.polyinfo_classifier` (never reimplements it) and adds the molecule's real chemistry on top; `guides/class_overrides.json` records the three documented departures from its label |
| `chemistry_policy.py` | Compares a repeat unit's actual chemistry against the constants its class carries. `polymer_class` is a BACKBONE taxonomy — polyinfo matches on the extracted mainchain, so a pendant hydroxyl, nitrile or ester never informed the label, and 404 of PI1070's 1077 real repeat units carry exactly such a group. Emits advisory findings (electrostatics, H-bond network, pendant polar chemistry, ionic species, measured EMC build risk); never rewrites a class constant |
| `headless_claude.py` | One `claude -p` call with structured output: the shared runner for the LangGraph driver's two model nodes. Read-only by construction (no Write/Edit, no MCP servers), so python performs every file write |

Two guides files back that pair, and they are deliberately NOT the same thing.
`guides/polymer_group_profile.json` mirrors RadonPy's 21 class-DEFINING SMARTS so the label
can be reproduced; it is regenerated from RadonPy's source by
`tools/class_profile/gen_polymer_group_profile.py` and never hand-edited.
`guides/functional_groups.json` is a 40-rule inventory of real functional groups that
describes the MOLECULE — matched over the whole repeat unit (on the 2-mer, so a group
spanning the cut is visible), each tagged backbone or pendant. The electrostatics implied by
that chemistry agrees with the class-declared value on all 43 curated `member_smiles`, which
is what makes a disagreement on a novel polymer worth reporting.

`orchestration/langgraph/` is the headless driver: `run_graph.py` runs a whole campaign —
classify, plan, critique, adjudicate, materialize, execute — with no live Claude Code session.
It is topology only. It decides *when* the scripts above run and never what they do, holds no
durable state of its own (the resume point is derived from `data/<run>/`, so there is no
checkpointer to drift), and reaches execution through `agent_api.py` exactly as a human would.
Two properties are load-bearing and easy to break: the graph is a **DAG** — `escalation_required`
and `failed` are terminal, because `MAX_AGENT_DECISIONS` is already spent by the time they are
returned — and **every** path into execution passes the cost guard, including resume.

`data/<run>/raw/control_state.json` is a thin session record -- which session is on this run
and whether it is over -- written by the control plane AND by the resume path, so it is not
frozen at the first call. Execution state lives in `data/<run>/workflow_state.json` (per-stage
status/attempts) and each attempt's own
`data/<run>/attempts/<stage>/<attempt_id>/executor_state.json` (the plan-level `decided_params` that were in force for that attempt, plus its computed outputs -- NOT the resolver's per-stage arguments, which are computed transiently and never persisted). Completed stages are skipped on resume. The recovery agent
is never called unless validation or a deterministic stage returns a structured issue.
