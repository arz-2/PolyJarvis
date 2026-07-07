# Data — Provenance for the Benchmark Systems

This directory holds a curated, openly browsable subset of the simulation provenance for
every benchmark replicate: workflow traces, prompts, tool calls, decision logs, input
scripts, final structures, seeds, and analysis outputs.

The full simulation tree is ~44 GB (atomistic trajectories). To keep this repository
browsable, **trajectories and checkpoints are NOT here** — they live in the archived release
(see *Not in this repository* below). Everything needed to inspect the agent's decisions,
re-run the simulations, and verify the analysis **is** here.

## Benchmark systems (36 replicate runs)

| Run dirs | Polymer | EMC class | Force field |
|---|---|---|---|
| `PE1`–`PE4` | Polyethylene | PHYC | TraPPE-UA |
| `PLA1`–`PLA4` | Poly(lactic acid) | PEST | PCFF |
| `PMMA1`–`PMMA4` | Poly(methyl methacrylate) | PACR | PCFF |
| `PEEK1`–`PEEK4` | Poly(ether-ether-ketone) | PKTN | PCFF |
| `PSU1`–`PSU4` | Polysulfone (Udel) | PSFO | PCFF |
| `cis-PBD1`–`cis-PBD4` | cis-Polybutadiene | PDIE | TraPPE-UA |
| `PVC1`–`PVC4` | Poly(vinyl chloride) | PVNL | PCFF |
| `PS1`–`PS4` | Atactic polystyrene | PSTR | PCFF |
| `PEG1`–`PEG4` | Poly(ethylene glycol) | POXI | PCFF |

Replicates differ by velocity/packing seed (recorded in each `run_log.md`) and, for some, by
Tg cooling-rate ladder. Replicates are reported as run-to-run spread, not best-of.

## What is in each `data/<run>/`

| Path | Contents |
|---|---|
| `run_log.md` | Per-run **decision log** (D-01…), recovery log, seeds, GPU/wall-time, results table |
| `Task.txt` | Run task metadata |
| `raw/*.json` | `run_plan.json` (agent decisions), `run_summary.json`, `equilibration_comprehensive.json` (Rg / MSD / density-homogeneity / C(t)), `equilibrated_density.json`, `tg_summary.json`, `tg_multirate_result.json`, `bulk_modulus*.json` (τ_eff, N_eff, block-SEM) |
| `raw/*.csv` | `tg_density_bins*.csv` (**raw Tg-fit data**), `volume_timeseries.csv`, `stress_strain.csv` |
| `raw/*.md`, `raw/*.txt` | `d05_block.md` (convergence diagnostics), `equil_prompt.txt` (planner prompt) |
| `graphs/*.png` | Tg fits (incl. per-rate `tg_r*/`), volume-fluctuation, Murnaghan-EOS, Born-matrix plots |
| `lammps/**/*.in` | **LAMMPS input scripts** for every stage (minimize → npt → tg sweep → mechanical) |
| `lammps/**/emc_build.params` | Force-field parameters (FF provenance) |
| `lammps/**/*.sh`, `lammps/**/*.jsonl` | Chain submit scripts + progress / tool-call traces |
| `lammps/**/*.log` | **Per-stage LAMMPS step logs** — committed for runs where they were retained (see *Log coverage* below) |
| `lammps/cell/cell.data` | Initial packed cell (starting structure) |
| `lammps/**/npt_production_out.data`, `**/npt_prod300_out.data` | **Final equilibrated structures** (rubbery: `npt_production`; glassy: `npt_prod300`) |

## Regenerating the selection and the derived analysis

[`manuscript/collect_data.sh`](../collect_data.sh) rebuilds this release end to end: it
auto-discovers every `manuscript/data/<run>/` directory, re-stages the provenance subset above, and then
re-derives the paper's analysis artifacts from it — the `manuscript/csv/` tables (per-replicate Tg
bins, bulk-modulus robustness, compute cost, structure diagnostics) and the derived figures.
Analysis is script-driven throughout (`manuscript/gen_*.py`); there are no notebooks.

Three csv families under `manuscript/csv/` are **source data** computed from the archived
trajectories rather than regenerable outputs: `<family>_rdf.csv`,
`density_homogeneity_300k.csv`, and `structure_diagnostics_300k_local.csv`.

## Not in this repository (in the archived release / DOI)

To stay within GitHub size limits, the following are **excluded** here and deposited in the
archived release accompanying the manuscript:

- Full atomistic **trajectories** (`*.dump`, ~44 GB),
- Binary **restart/checkpoint** files (`*.restart`, `*.rst`),
- **Intermediate-stage** structures (minimize / compress / cool / pppm / softheat / melt
  `*_out.data`) — deterministically reproducible from the `.in` scripts + seeds above.

### Log coverage

Per-stage LAMMPS step **logs** (`*.log`) are committed for **all 36 runs**, wherever they
were retained locally; every run includes its equilibration-stage logs. Any individual stage
log that is absent was not retained at run time — its **thermodynamic content is fully
preserved** in `raw/*.csv` and `raw/*.json` (density / volume timeseries, Tg-fit bins,
stress-strain, convergence diagnostics), and the stage is deterministically reproducible from
the committed `.in` scripts + seeds. Full atomistic trajectories remain in the archived
release for all runs.

### Directory layout

Every run follows the same `lammps/` skeleton: `cell/` (initial packed cell + FF params),
`equil/<stage>/` (equilibration chain), `thermal/` (Tg sweeps), `mechanical/` (bulk-modulus
runs). Six early runs (`PE3`, `PMMA1`, `PEEK2`, `PEEK3`, `PSU1`, `cis-PBD3`) originally used a
flat layout (stages directly under `lammps/`) and were normalized to this skeleton after the
fact — paths quoted *inside* their `run_log.md`, chain `.sh` scripts, and LAMMPS logs may
therefore reference the original flat locations.

These runs executed under the repository's live working directory `data/<run>/` and were
archived here (`manuscript/data/<run>/`) afterwards, so repo-relative paths quoted inside run
logs, chain scripts, and LAMMPS logs use the original `data/<run>/...` prefix.

A local-only `archive/` directory (not committed) sits alongside the run dirs; it holds
analysis summaries from superseded early exploratory runs that predate the 36-run benchmark
and is not part of the study.

## Prompts, tool schemas, and the agent

These are part of the codebase, not under `data/`:

- **Worker prompts** are generated by [`scripts/gen_prompt.py`](../../scripts/gen_prompt.py) from
  the stage guides in [`guides/`](../../guides/) and the per-class rules in
  [`guides/polymer_rules.json`](../../guides/polymer_rules.json).
- **Tool schemas** (typed MCP tools the agent calls) are defined by the MCP servers under
  `mcp-servers/`.
- The orchestrator/worker architecture is documented in [`CLAUDE.md`](../../CLAUDE.md).
