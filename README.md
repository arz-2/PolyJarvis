# PolyJarvis

**PolyJarvis** is an AI-driven framework for autonomous polymer property prediction via all-atom molecular dynamics simulation. A researcher describes a polymer system in natural language; a stateful LLM orchestrator (Claude) then handles the entire workflow — from SMILES string to computed material properties — by planning the run, spawning specialist sub-agents for each stage, and driving three MCP servers (molecular construction via EMC/RadonPy, plus local GPU simulation and analysis) end to end.

![PolyJarvis Architecture](manuscript/figures/figure1_architecture.png)

---

## Architecture

PolyJarvis is a **stateful orchestrator driving a fleet of stateless specialist agents** over a Model Context Protocol (MCP) tool layer. Given a SMILES string (or polymer name) and a set of target properties, it autonomously runs the full pipeline — construction → equilibration → property campaigns → experiment-validated reporting — on a local 4× Quadro RTX 6000 GPU node.

**Orchestration layer.** A single long-lived Claude session (the *orchestrator*) holds all run state, recovery logic, and the approved plan. It never runs simulations itself; it spawns workers and routes their results. Workers are **stateless** — each gets a self-contained prompt and returns a structured RESULT block — so the orchestrator is the only stateful component and the sole point of recovery. [`CLAUDE.md`](CLAUDE.md) is its operating manual and the authoritative worker roster.

**Agent layer (13 specialist workers).** Each worker has a fixed role, a model tier matched to task difficulty, and a canonical guide inlined into its prompt by `orchestration/gen_prompt.py`:

| Phase | Workers (model) |
|-------|-----------------|
| Setup | `literature-grounding-worker` (sonnet), `planner` (opus), `critic` (opus) |
| Foundation | `molecule-builder` (opus), `equilibration-worker` (sonnet), `equilibration-checker` (haiku) |
| Thermal track | `tg-sweep-worker`, `tg-analysis-worker` (haiku) |
| Mechanical track | `murnaghan-worker`, `deform-worker` (haiku), `bulk-modulus-extractor` (sonnet) |
| Summary | `exp-lookup-worker`, `run-summary-worker` (haiku) |

**Tool layer (three MCP servers).** `mcp-emc-server` (EMC amorphous-cell builder covering 20 polymer classes, auto-selecting PCFF / OPLS-AA / TraPPE-UA per class), `mcp-lammps-engine` (GPU LAMMPS execution + analysis), and `mcp-mol-builder-server` (RadonPy path — the builder fallback for the one class EMC cannot type, polyureas).

### Control flow: plan → critique → execute → validate

1. **Ground & Plan.** For off-table or low-confidence chemistries, a grounding worker produces a DOI-verified evidence file; the planner emits a `run_plan.json`. High-confidence classes get a **deterministic, byte-identical plan** with no runtime LLM reasoning.
2. **Critique.** A critic adjudicates the plan (approve / revise / escalate), looping up to two rounds. Deterministic plans pass in round 1 with zero findings.
3. **Execute by track.** The **foundation** track always runs first (build → equilibrate → equil-check gate → density). The property-conditional tracks then run against the equilibrated cell: **thermal** (multi-rate T<sub>g</sub> sweeps → T<sub>g</sub>, CTE, ΔC<sub>p</sub>) and **mechanical** (Murnaghan pressure-series EOS as the primary bulk-modulus path, 3-direction uniaxial deformation as the fallback → K). Mechanical reads the glassy/rubbery regime from thermal.
4. **Validate.** Every worker result is checked against the plan's `success_criteria`; failures trigger bounded recovery (max 2 attempts/worker) before the run is marked UNRESOLVED. A condition-matched experimental lookup supplies grading bounds before the final summary.

The **`run_plan.json` is the single source of truth** — `orchestration/gen_prompt.py` threads its `decided_params` into every worker prompt, so no worker improvises parameters and the whole run is reconstructable from the plan. What gets reported, and how each property is computed, is documented in [`docs/PROPERTIES.md`](docs/PROPERTIES.md).

### Inferred vs. inherited

- **Inherited / encoded** (in `guides/polymer_rules.json`, `guides/decision_policy.json`, stage guides): per-class T<sub>g</sub>/density targets, DP defaults, force-field family rules, SMILES conventions, equilibration templates. On the high-confidence path these drive a fully deterministic plan.
- **LLM-inferred at runtime**: off-table planning, critic adjudication, error root-causing and recovery routing, and adaptive extensions (equilibration EXTEND, T<sub>g</sub> slope-gate recovery).

Below is a sample conversation between a user and the agent:
![Conversation](manuscript/figures/figure2_conversation.png)

---

## Benchmark study

The framework was validated on a **36-run replicate study: 9 polymers × 4 independent replicates** (PE, cis-PBD, PEG, PLA, PMMA, PS, PVC, PEEK, PSU), reporting density, T<sub>g</sub>, and bulk modulus against experimental ranges. All manuscript-related material — the replicate-run provenance, analysis csv/figures and their generators, and the error-recovery benchmark — is consolidated under [`manuscript/`](manuscript/); the run provenance is indexed in [`manuscript/data/README.md`](manuscript/data/README.md).

---

## Repository Map

| Path | What lives there |
|---|---|
| `CLAUDE.md` | Orchestrator operating manual — the agent's workflow spec (start here to understand the pipeline) |
| `.claude/` | Agent definitions (13 workers), hooks, slash commands, per-agent memory |
| `guides/` | **Agent prompts & machine-read config**, not human docs — worker guides inlined by `gen_prompt.py`, orchestrator track guides, `polymer_rules.json` / `decision_policy.json` (see [`guides/README.md`](guides/README.md)) |
| `orchestration/` | CLI/orchestration helpers — prompt generation, deterministic planning, GPU allocation (see [`orchestration/README.md`](orchestration/README.md)) |
| `mcp-servers/` | The three MCP servers: `mcp-mol-builder-server` (RadonPy), `mcp-emc-server` (EMC), `mcp-lammps-engine` (LAMMPS + analysis scripts + templates) |
| `data/` | Live pipeline working directory — per-run simulation outputs (`<run>/run_log.md`, `lammps/`, `raw/`, `graphs/`), run template |
| `hardware/` | Hardware calibration — `/calibrate-hardware` toolchain (`calibrate_hardware.py`, `benchmark_hardware.py`, `bench_accuracy_diff.py`) and the per-FF calibration cells (`CALIB_<FAM>/`); the engine/GPU/MPI policy docs (`HARDWARE.md`, `HARDWARE_STUDY.md`) are machine-specific and local-only (gitignored) |
| `db/` | Experimental property database (`polymer_db.sqlite`, schema, query + ingest scripts) |
| `tests/`, `mcp-servers/*/tests/`, `tools/runlog_miner/tests/` | Test suites (root `pytest.ini`); the recovery-benchmark suite is run separately (`pytest manuscript/recovery/tests/`) |
| `tools/runlog_miner/` | Run-log mining/reporting package |
| `docs/` | Human-facing docs: `PROPERTIES.md` (what gets computed & how), `ROADMAP.md`, `TOOLS_REFERENCE.md` |
| `env/` | Conda environment YAMLs |
| `manuscript/` | Everything paper-related: benchmark-run provenance (`data/`, see [`manuscript/data/README.md`](manuscript/data/README.md)), analysis tables (`csv/`), figures + generator scripts, the error-recovery benchmark (`recovery/`), and the data-release rebuilder (`collect_data.sh`) |

---

## Quick Start

New to the repo? The fastest path to a first run:

1. **Read [`guides/README.md`](guides/README.md)** — the navigation hub for the whole pipeline.
2. **Complete [Setup](#setup) below** — build LAMMPS (GPU), create the conda envs, install EMC, configure `.mcp.json` (Claude Code launches the three MCP servers from it automatically).
3. **Calibrate once on a new machine:** run `/calibrate-hardware` (see [Hardware Calibration](#hardware-calibration-first-run-on-a-new-machine)).
4. **Ask the agent in natural language** (see [Usage](#usage)) — copy `Task_TEMPLATE.txt`, fill in a polymer name + SMILES, and describe what you want.

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

### Hardware Calibration (first run on a new machine)

Each run's `engine`/`mpi`/`gpu` defaults come from `guides/polymer_rules.json:hardware_policy`, and the right engine choice is hardware-dependent — so after cloning onto new hardware, host-match the defaults once (runs still work on the shipped defaults until you do; they're just directional, not measured-for-you):

```bash
python3 hardware/calibrate_hardware.py --dry-run   # preview the polite plan per FF; writes nothing
nice -n 19 python3 hardware/calibrate_hardware.py  # measure + write hardware_policy
python3 orchestration/pick_gpu.py status                 # verify: GPU allocation / spare-core view
```

Calibration is **polite by default** on a shared box: idle GPUs only, rank caps against measured CPU load, everything `nice`d — never use `--allow-busy`. The calibration cells ship in-repo (`hardware/CALIB_<FAM>/`). Re-run after any GPU/CPU change. Measured results and the per-FF lookup table are kept in machine-specific notes (`hardware/HARDWARE.md`, `hardware/HARDWARE_STUDY.md`; local-only, gitignored). An agent can drive the whole procedure via the `/calibrate-hardware` slash-command.

---

## Usage

Open Claude Code in the `PolyJarvis/` directory and describe your polymer:

> *"Run a full MD simulation of PVDF. SMILES: \*CC(F)(F)\*. I want Tg and equilibrated density."*

The agent reads `CLAUDE.md` automatically on every task, classifies the polymer, selects the correct force field and builder, plans and critiques the run, builds the amorphous cell, equilibrates, runs the requested property tracks, and reports results graded against experiment — all without manual intervention.

To start a new simulation, copy `Task_TEMPLATE.txt` and fill in the polymer name and SMILES.

---

## Tech Stack

| Component | Library / Tool |
|-----------|---------|
| Molecular construction (GAFF2) | RadonPy, RDKit |
| Quantum chemistry (charges) | Psi4 / xTB (GFN2 AM1-BCC fallback) |
| Amorphous cell builder (PCFF) | EMC v9.4.4 (Pieter in 't Veld) |
| Force fields | GAFF2, GAFF2_mod (RadonPy) · OPLS-AA, TraPPE-UA, PCFF (EMC) |
| MD simulation | LAMMPS (GPU + KOKKOS builds, class2 styles) |
| Trajectory analysis | MDAnalysis |
| T<sub>g</sub> fitting | SciPy (F-stat exhaustive split) |
| MCP framework | FastMCP |

---

## License

See [LICENSE](LICENSE).
