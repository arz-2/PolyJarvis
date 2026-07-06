# PolyJarvis

**PolyJarvis** is an AI-driven framework for autonomous polymer property prediction via all-atom molecular dynamics simulation. A researcher describes a polymer system in natural language; a stateful LLM orchestrator (Claude) then handles the entire workflow — from SMILES string to computed material properties — by planning the run, spawning specialist sub-agents for each stage, and driving three MCP servers (molecular construction via EMC/RadonPy, plus local GPU simulation and analysis) end to end.

![PolyJarvis Architecture](figures/figure1_architecture.png)

---

## Architecture

PolyJarvis is a **stateful orchestrator driving a fleet of stateless specialist agents** over a Model Context Protocol (MCP) tool layer. Given a SMILES string (or polymer name) and a set of target properties, it autonomously runs the full pipeline — construction → equilibration → property campaigns → experiment-validated reporting — on a local 4× Quadro RTX 6000 GPU node.

### Three layers

**Orchestration layer.** A single long-lived Claude session (the *orchestrator*) holds all run state, recovery logic, and the approved plan. It never runs simulations itself; it spawns workers and routes their results. Workers are **stateless** — each gets a self-contained prompt and returns a structured RESULT block — so the orchestrator is the only stateful component and the sole point of recovery.

**Agent layer (14 specialist workers).** Each worker has a fixed role, a model tier matched to task difficulty, and a canonical guide inlined into its prompt:

| Phase | Workers (model) |
|-------|-----------------|
| Setup | `literature-grounding-worker` (sonnet), `planner` (opus), `critic` (opus) |
| Foundation | `molecule-builder` (opus), `equilibration-worker` (sonnet), `equilibration-checker` (haiku) |
| Thermal track | `tg-sweep-worker`, `tg-analysis-worker` (haiku) |
| Mechanical track | `murnaghan-worker`, `deform-worker` (haiku), `bulk-modulus-extractor` (sonnet) |
| Summary | `exp-lookup-worker`, `run-summary-worker` (haiku) |

**Tool layer (three MCP servers).** Standardized, discoverable tool interfaces the agents invoke: `mcp-emc-server` (EMC amorphous-cell builder, 20 polymer classes, auto-selecting PCFF / OPLS-AA / TraPPE-UA), `mcp-lammps-engine` (GPU LAMMPS execution + analysis), and the `mcp-mol-builder-server` RadonPy path (builder fallback for classes EMC cannot type).

### Control flow: plan → critique → execute → validate

1. **Ground & Plan.** For off-table or low-confidence chemistries, a grounding worker produces a DOI-verified evidence file; the planner emits a `run_plan.json`. High-confidence classes get a **deterministic, byte-identical plan** with no runtime LLM reasoning.
2. **Critique.** A critic adjudicates the plan (approve / revise / escalate), looping up to two rounds. Deterministic plans pass in round 1 with zero findings.
3. **Execute by track.** Foundation runs first (build → equilibrate → density), then the property-conditional **thermal** and **mechanical** tracks run against the equilibrated cell. Mechanical reads the glassy/rubbery regime from thermal.
4. **Validate.** Every worker result is checked against the plan's `success_criteria`; failures trigger bounded recovery (max 2 attempts/worker) before the run is marked UNRESOLVED. A condition-matched experimental lookup supplies grading bounds before the final summary.

The **`run_plan.json` is the single source of truth** — `scripts/gen_prompt.py` threads its `decided_params` into every worker prompt, so no worker improvises parameters and the whole run is reconstructable from the plan.

### Inferred vs. inherited

- **Inherited / encoded** (in `guides/polymer_rules.json`, `guides/decision_policy.json`, stage guides): per-class T<sub>g</sub>/density targets, DP defaults, force-field family rules, SMILES conventions, equilibration templates. On the high-confidence path these drive a fully deterministic plan.
- **LLM-inferred at runtime**: off-table planning, critic adjudication, error root-causing and recovery routing, and adaptive extensions (equilibration EXTEND, T<sub>g</sub> slope-gate recovery).

### Execution pipeline

Within a run, the workers drive four sequential stages, each backed by MCP tools the agent calls directly:

```
SMILES string
     │
     ▼
┌─────────────────────────────────────────────┐
│  STAGE 1 · Molecular Construction          │
│                                             │
│  RadonPy path (GAFF2/OPLS-AA):             │
│  classify_polymer → build_molecule →        │
│  assign_charges → polymerize →              │
│  assign_forcefield → generate_cell →        │
│  save_lammps_data                           │
│                                             │
│  EMC path (PCFF — for PCBN/PAMD/PKTN/      │
│  PSFO/PIMD only):                           │
│  classify_polymer → submit_emc_cell_job     │
└────────────────────┬────────────────────────┘
                     │  .data file
                     ▼
┌─────────────────────────────────────────────┐
│  STAGE 2 · Equilibration                   │
│  LAMMPS Engine MCP Server (local GPU)      │
│                                             │
│  generate_equilibration_workflow(           │
│    use_pcff=True|False) →                  │
│  run_lammps_chain (6-stage auto protocol)  │
│  minimize → softheat → compress →           │
│  npt_pppm → cool → nvt_production          │
└────────────────────┬────────────────────────┘
                     │  equilibrated cell
                     ▼
┌─────────────────────────────────────────────┐
│  STAGE 3 · T_g Measurement                 │
│  Temperature sweep T_start → 300K          │
│  (25–20K steps, 0.5–1 ns/T)               │
│  extract_thermal → Tg + CTE + ΔCp          │
└────────────────────┬────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────┐
│  STAGE 4 · Property Extraction & Validation │
│  extract_equilibrated_density               │
│  extract_bulk_modulus (volume fluctuation)  │
│  calculate_rdf · extract_end_to_end_vectors │
│  check_equilibration_extended (Rg/MSD/P2)  │
│  Compare to experimental benchmarks         │
└─────────────────────────────────────────────┘
```
Below is a sample conversation between a user and the agent:
![Conversation](figures/figure2_conversation.png)

---

## Repository Map

| Path | What lives there |
|---|---|
| `CLAUDE.md` | Orchestrator operating manual — the agent's workflow spec (start here to understand the pipeline) |
| `.claude/` | Agent definitions (13 workers), hooks, slash commands, per-agent memory |
| `guides/` | **Agent prompts & machine-read config**, not human docs — worker guides inlined by `gen_prompt.py`, orchestrator track guides, `polymer_rules.json` / `decision_policy.json` (see [`guides/README.md`](guides/README.md)) |
| `scripts/` | CLI/orchestration helpers — prompt generation, deterministic planning, GPU allocation, hardware calibration (see [`scripts/README.md`](scripts/README.md)) |
| `mcp-servers/` | The three MCP servers: `mcp-mol-builder-server` (RadonPy), `mcp-emc-server` (EMC), `mcp-lammps-engine` (LAMMPS + analysis scripts + templates) |
| `data/` | Per-run simulation outputs (`<run>/run_log.md`, `lammps/`, `raw/`, `graphs/`); mostly git-excluded — the tracked subset is the reviewer provenance release (see `data/REVIEWER_DATA_README.md`) |
| `db/` | Experimental property database (`polymer_db.sqlite`, schema, query + ingest scripts; local only) |
| `benchmarks/recovery/` | Error-recovery benchmark (see its README) |
| `tests/`, `mcp-servers/*/tests/`, `benchmarks/recovery/tests/`, `tools/runlog_miner/tests/` | Test suites (root `pytest.ini`) |
| `tools/runlog_miner/` | Run-log mining/reporting package |
| `docs/` | Human-facing docs: `PROPERTIES.md` (what gets computed & how), `ROADMAP.md`, specs |
| `figures/` | Output of `paper/gen_figure{1,2}*.py`; included by the manuscript |
| `env/` | Conda environment YAMLs |
| `literature/`, `paper/` | Reference PDFs and manuscript sources (local only, git-excluded) |

---

## Quick Start

New to the repo? The fastest path to a first run:

1. **Read [`guides/README.md`](guides/README.md)** — the navigation hub for the whole pipeline.
2. **Complete [Setup](#setup) below** — build LAMMPS (GPU), create the conda envs, install EMC, configure `.mcp.json`.
3. **Start the three MCP servers** (see [Starting the MCP Servers](#starting-the-mcp-servers)).
4. **Calibrate once on a new machine:** run `/calibrate-hardware` (see [Hardware Calibration](#hardware-calibration-first-run-on-a-new-machine)).
5. **Ask the agent in natural language** (see [Usage](#usage)) — copy `Task_TEMPLATE.txt`, fill in a polymer name + SMILES, and describe what you want.

What gets reported, and how each property is computed, is documented in [`docs/PROPERTIES.md`](docs/PROPERTIES.md).

---

## Setup

### Prerequisites

Install the following before starting:

**1. Miniforge (conda)**
```bash
wget https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh
bash Miniforge3-Linux-x86_64.sh
```

**2. LAMMPS with GPU support**
```bash
# Build with MOLECULE, KSPACE, CLASS2, GPU packages
# See https://docs.lammps.org/Build_cmake.html
# Confirm: lmp -h | grep GPU
```

**3. mol-builder environment**
```bash
conda create -n mol-builder python=3.9
conda activate mol-builder
pip install radonpy rdkit psi4 mdanalysis fastmcp xtb-python
pip install -e /path/to/RadonPy
```

**4. EMC (Enhanced Monte Carlo)**
```bash
# Download EMC from http://montecarlo.sourceforge.net/emc/
# Extract to ~/emc; add ~/emc/bin to PATH in ~/.bashrc
# Verify: emc_setup.pl --help
```

**5. Claude Code CLI**
```bash
npm install -g @anthropic-ai/claude-code
```

### Configuration

Create `PolyJarvis/.env` (single file shared by all servers):

```env
LAMBDA_USER     = <your_username>
LAMBDA_WORKDIR  = /home/<user>/simulations
LAMBDA_LAMMPS   = /home/<user>/lammps-install/bin/lmp
CONDA_ENV       = mol-builder
RADONPY_PATH    = /path/to/RadonPy
```

MDAnalysis analysis scripts are bundled inside `mcp-lammps-engine/analysis_scripts/` — no separate `MDA_SCRIPTS_DIR` needed.

### Starting the MCP Servers

The servers are launched automatically by Claude Code via `.mcp.json`. To start them manually for debugging:

```bash
# mol-builder server
/home/<user>/miniforge3/envs/mol-builder/bin/python \
  PolyJarvis/mcp-servers/mcp-mol-builder-server/server.py

# EMC server
PolyJarvis/mcp-servers/.venv/bin/python \
  PolyJarvis/mcp-servers/mcp-emc-server/server.py

# LAMMPS engine server
PolyJarvis/mcp-servers/.venv/bin/python \
  PolyJarvis/mcp-servers/mcp-lammps-engine/server.py
```

See `PolyJarvis/.mcp.json` for the registered server configuration.

### Hardware Calibration (first run on a new machine)

PolyJarvis derives each run's `engine`/`mpi`/`gpu` defaults from
`guides/polymer_rules.json:hardware_policy` (consumed by `scripts/gen_prompt.py`). The engine
choice is **hardware-dependent** (KOKKOS wins for PPPM forcefields but loses on small UA cells on
some GPUs; another GPU/core-count can flip the winner) — so after cloning onto new hardware, run
`/calibrate-hardware` once to **host-match** the defaults. Until you do, runs still work on the
shipped defaults (a one-line `gen_prompt` nudge reminds you), they're just directional, not
measured-for-you. The calibration cells ship in-repo (`data/CALIB_<FAM>/`), so no build is needed.

> **Shared box?** Calibration is **polite by default**: it only uses GPUs that are idle *and* free
> of any other user's compute process, caps MPI ranks against measured CPU load (leaving ≥25 % of
> cores free), runs everything `nice`d and sequentially, and skips work that would contend. A
> contended / parity-failing run records evidence but leaves `values_are_benchmarked: false` —
> re-run on an idle window for the authoritative flip. Never use `--allow-busy` on a shared machine.

**0. Prerequisites:** LAMMPS (GPU build; optionally a KOKKOS build at `LAMBDA_LAMMPS_KOKKOS` to
unlock the kokkos engine — absent, the kokkos FFs fall back to the GPU package) and the env from the
Setup steps above must work.

**1. Revalidate the shipped defaults on this box** (the default mode — confirms the engine choice +
records host-matched ns/day; no engine re-search):

```bash
python3 scripts/calibrate_hardware.py --dry-run    # preview the polite plan per FF; writes nothing
nice -n 19 python3 scripts/calibrate_hardware.py   # measure + write hardware_policy (drop --dry-run)
```

It auto-detects your GPU count/model and cores, runs each FF's shipped default on the in-repo cell
(timed → ns/day) plus a run-0 parity vs CPU, and writes back the `host` fingerprint,
`directional_probe` evidence, and — on a clean host-matched pass — flips `values_are_benchmarked:
true`. (`data/CALIB_OPLS/` and `data/CALIB_GAFF/` build once via EMC if absent; see the
`/calibrate-hardware` skill.)

**2. Verify:**

```bash
python3 -c "import json;hp=json.load(open('guides/polymer_rules.json'))['hardware_policy'];print(hp['host'], hp['values_are_benchmarked'])"
python3 scripts/pick_gpu.py status        # GPU allocation / spare-core view
```

**When to re-run:** any GPU or CPU change, or moving to a different machine. To re-derive the engine
*winner* (not just confirm the shipped choice) on very different hardware, use `--full` with explicit
`--cell`/`--ff` pairs on a drained box. See
[`guides/HARDWARE.md`](guides/HARDWARE.md) for the per-FF lookup table and
[`guides/HARDWARE_STUDY.md`](guides/HARDWARE_STUDY.md) for the rationale. An agent can drive
this whole procedure via the `/calibrate-hardware` slash-command.

---

## Usage

Open Claude Code in the `PolyJarvis/` directory and describe your polymer:

> *"Run a full MD simulation of PVDF. SMILES: \*CC(F)(F)\*. I want Tg and equilibrated density."*

The agent reads `CLAUDE.md` automatically on every task, classifies the polymer, selects the correct force field and builder, builds the amorphous cell, equilibrates, runs the Tg sweep, and reports results — all without manual intervention.

To start a new simulation, copy `Task_TEMPLATE.txt` and fill in the polymer name and SMILES.

---

## Tech Stack

| Component | Library / Tool |
|-----------|---------|
| Molecular construction (GAFF2) | RadonPy, RDKit |
| Quantum chemistry (charges) | Psi4 / xTB (GFN2 AM1-BCC fallback) |
| Amorphous cell builder (PCFF) | EMC v9.4.4 (Pieter in 't Veld) |
| Force fields | GAFF2, GAFF2_mod (RadonPy) · OPLS-AA, TraPPE-UA, PCFF (EMC) |
| MD simulation | LAMMPS (GPU build, class2 styles) |
| Trajectory analysis | MDAnalysis |
| T<sub>g</sub> fitting | SciPy (F-stat exhaustive split) |
| MCP framework | FastMCP |

---

## License

See [LICENSE](LICENSE).
