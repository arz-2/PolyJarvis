# PolyJarvis

PolyJarvis is a deterministic polymer-simulation platform with an optional agentic scientific
control layer. Agents choose goals and handle unusual failures; executable code owns simulation
files, parameter resolution, job submission, validation, recovery limits, and provenance.

## Architecture

```text
scientific intent -> planning agent -> validated run_plan.json
                                      |
                                      v
                         deterministic stage scripts
                                      |
                         success -----+----- issue
                                            |
                                            v
                                      recovery agent
```

The runtime source of truth is code and machine-readable configuration:

- `orchestration/scripts/agent_api.py` is the small agent-facing contract.
- `orchestration/scripts/scientific_control.py` enforces planning, execution, and recovery order.
- `orchestration/scripts/run_campaign.py` executes and resumes the workflow.
- `orchestration/scripts/stage_params.py` resolves plans into concrete tool arguments.
- `orchestration/scripts/protocol_policy.py` owns bounded recovery and pressure selection.
- `guides/polymer_rules.json` contains versioned polymer and hardware configuration.
- `mcp-servers/` contains builders, LAMMPS templates, parsers, and analysis functions.

There are no stage worker prompts and no agent-owned simulation state. The prior multi-agent
implementation and manuscript archive remain available in Git history on `main`.

## Agent Contract

```bash
python3 orchestration/scripts/agent_api.py contract
python3 orchestration/scripts/agent_api.py inspect RUN_NAME
```

The contract requires scientific planning before execution and proves recovery is issue-triggered.
The complete JSON schemas are documented in `docs/AGENT_CONTRACT.md`.

## Plan and Run

Connect a model-provider wrapper that reads one JSON object from stdin and returns the planning
decision JSON described in `docs/AGENT_CONTRACT.md`:

```bash
python3 orchestration/scripts/scientific_control.py \
  --run-name PS1 \
  --goal 'Compute density, Tg, and bulk modulus at 300 K' \
  --smiles '*CC(*)c1ccccc1' \
  --properties density,tg,bulk_modulus \
  --polymer-class-hint PSTR \
  --scientific-agent-command 'python /path/to/scientific_agent.py' \
  --recovery-agent-command 'python /path/to/recovery_agent.py'
```

For an audited decision replay or dry-run, use a captured decision file:

```bash
python3 orchestration/scripts/scientific_control.py \
  --run-name PS1 \
  --goal 'Compute density, Tg, and bulk modulus at 300 K' \
  --smiles '*CC(*)c1ccccc1' \
  --properties density,tg,bulk_modulus \
  --decision-file examples/pstr_decision.json \
  --dry-run
```

The control layer persists `control_state.json`; deterministic stages persist
`executor_state.json`. Successful runs never invoke the recovery command. Remove `--dry-run` to
execute the simulation chain.

## Scientific Workflow

The default campaign is deterministic:

```text
build -> finite-size validation -> equilibrate -> convergence gate
      -> density -> Tg (when requested) -> Murnaghan/deformation (when requested)
      -> experimental comparison -> run summary
```

The runner launches build, equilibration, thermal, mechanical, and summary as separate resumable
commands. Safe deterministic `EXTEND` recovery remains code-owned. Novel failures become
structured issues for the recovery agent, capped at two calls. Murnaghan pressure ladders come
from class configuration, CED screening when available, or a conservative unscreened probe.

## Setup

The simulation host needs LAMMPS, EMC, and the dependencies in
`mcp-servers/requirements.txt`. Copy `.mcp.json.example` to `.mcp.json` and set host-specific
paths. Hardware defaults can be calibrated with:

```bash
python3 hardware/calibrate_hardware.py --dry-run
```

## Tests

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/pytest -v
```

Tests marked `requires_binaries` need a configured simulation host.

## License

See `LICENSE`.
