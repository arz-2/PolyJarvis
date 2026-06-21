# PolyJarvis

**PolyJarvis** is an AI-driven framework for autonomous polymer property prediction via all-atom molecular dynamics simulation. A researcher describes a polymer system in natural language; an LLM agent (Claude) then handles the entire workflow — from SMILES string to computed material properties — by orchestrating two MCP servers: one for molecular construction and one for remote GPU simulation.

![PolyJarvis Architecture](figures/figure1_architecture.png)

---

## Overview

Traditional polymer MD workflows require manual intervention across several software environments (RDKit, RadonPy, LAMMPS, MDAnalysis) and substantial domain expertise to set up correctly. PolyJarvis automates this end-to-end by giving an LLM agent structured tools for each stage, along with documented decision rules (force field selection, convergence thresholds, fit quality checks) that ensure physical correctness without hand-holding.

### Properties computed

- Glass transition temperature (T<sub>g</sub>) via density–temperature sweep with bilinear fit
- Equilibrated density at target T and P
- Isothermal bulk modulus via volume fluctuation method
- Radial distribution functions (RDF) for structural analysis
- End-to-end vector distributions for chain conformation analysis

---

## Architecture

The system is organized into four sequential stages, each backed by MCP tools the agent can call directly:

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

## Repository Structure

```
PolyJarvis/
├── guides/                         # Stage-by-stage execution guides (READ FIRST)
│   ├── STAGE_INDEX.md              # Navigation hub — start here
│   ├── STAGE_1_MOLECULAR_CONSTRUCTION.md
│   ├── STAGE_2_EQUILIBRATION.md
│   ├── STAGE_3_TG_MEASUREMENT.md
│   ├── STAGE_4_ANALYSIS.md
│   ├── TOOLS_REFERENCE.md          # Complete MCP tool signatures
│   ├── ROADMAP.md                  # Force field expansion (Tracks A–E)
│   └── polymer_rules.json          # Per-class FF, builder, confidence metadata
├── mcp-servers/
│   ├── mcp-mol-builder-server/         # Mol-Builder server (GAFF2/OPLS-AA path)
│   │   ├── server.py               # 20+ MCP tools
│   │   └── patch_fluorine_params.py  # PHAL LJ patch (Watkins & Jorgensen 2001)
│   ├── mcp-emc-server/             # PCFF amorphous cell builder (EMC wrapper)
│   │   ├── server.py               # 4 MCP tools (PCBN/PAMD/PKTN/PSFO/PIMD)
│   │   ├── smiles_to_emc.py        # SMILES → EMC .esh → LAMMPS .data pipeline
│   │   └── tests/                  # Unit tests (35 passing, all 5 PCFF classes)
│   └── mcp-lammps-engine/          # Simulation & analysis (LAMMPS)
│       ├── server.py               # 25 MCP tools
│       ├── script_generator.py     # Template filler — GAFF2, OPLS-AA, PCFF
│       ├── analysis_scripts/       # Bundled MDAnalysis scripts (extract_thermal, RDF, MSD…)
│       └── templates/              # 9 validated LAMMPS script templates
├── data/                           # Completed example runs
│   ├── PE{1,2,3}/                  # Polyethylene
│   ├── PEG{1,2,3}/                 # Poly(ethylene glycol)
│   ├── PMMA{1,2,3}/                # Poly(methyl methacrylate)
│   └── PS{1,2,3}/                  # Polystyrene
├── figures/
│   └── figure1_architecture.png
└── Task_TEMPLATE.txt               # Template for specifying new simulation tasks
```

---

## MCP Servers

### `mcp-mol-builder-server` (local)

Wraps [RadonPy](https://github.com/RadonPy/RadonPy) for molecule construction. Handles the full GAFF2/OPLS-AA path: monomer build → charge assignment → polymerization → amorphous cell → LAMMPS `.data` file. Runs in the `mol-builder` conda environment.

### `mcp-emc-server` (local)

Wraps [EMC](http://montecarlo.sourceforge.net/emc/) for PCFF amorphous cell construction. Used only for PCBN, PAMD, PKTN, PSFO, and PIMD classes. Outputs a LAMMPS `.data` file with PCFF parameters assigned — no separate charge step needed.

### `mcp-lammps-engine` (local)

Script generation, simulation execution, and analysis on the local GPU server. Simulation chains run as `nohup` processes and survive MCP server disconnections. Bundles all MDAnalysis analysis scripts in `analysis_scripts/`.


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

The agent reads `guides/STAGE_INDEX.md` automatically on every task, classifies the polymer, selects the correct force field and builder, builds the amorphous cell, equilibrates, runs the Tg sweep, and reports results — all without manual intervention.

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
