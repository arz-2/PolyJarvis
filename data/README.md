# Run data

This folder holds the run workspaces behind every number in the manuscript and SI. `data/*` is
gitignored, and the folders below were force-added. Trajectories (`.dump`, `.dump.gz`), binary
restarts (`.rst`, `.restart`) and launcher PID files are not included.

Of the LAMMPS structure files (`.data`), only the cells that reported numbers come from are
included; `tools/key_structures.py` lists them. They are the built cell, the melt-hold output
that cooling and the Tg staircase start from, the 300 K cell that density and the bulk-modulus
series start from, and the output of each bulk-modulus pressure point. For a run that ended in
equilibration, the melt-hold output of its last attempt is included. Tg legs start from their
anchor run's melt cell and have no structures of their own.

## What is here

| Folder | Used for | Host |
|---|---|---|
| `PE_1`–`3`, `PEG_1`–`3`, `PEEK_1`–`3`, `PSU_1`–`3` | validation campaign, three replicates each | A800 |
| `PLLA_1`–`3`, `aPS_1`–`3`, `sPVC_1`–`3` | validation campaign, three replicates each | RTX 6000 |
| `PEG_COMPASS_1`–`3` | PEG under COMPASS, seed-paired to `PEG_1`–`3` (SI S4) | A800 |
| `PTFE_AI`, `PTFE_noAI` | agent ablation on PTFE (main text; SI S6) | RTX 6000 |
| `tg_sensitivity/TGS_PE_1_*` | PE Tg legs: cooling rate and temperature step (SI S4) | A800 |
| `tg_sensitivity/TGS_PLLA_1_*` | PLLA Tg legs (SI S4) | RTX 6000 |
| `bm_diagnostics_r2` | controlled bulk-modulus legs on the `sPVC_3` cell (SI S4); legs and analysis in `benchmarks/bm_diagnostics_r2` | RTX 6000 |
| `peg_size_v1` | PEG 10- vs 20-chain bulk-modulus pair, earlier protocol (SI S4); see its README | RTX 6000 |

`manuscript/gen/replicates.py` defines the reported run set, and every table and figure generator
in `manuscript/gen/` reads from these folders.

## Layout of a run

```
<run>/
  workflow_state.json      stage status, accepted attempt and input hash per stage
  recovery_log.jsonl       remedy and agent events (present only if any occurred)
  raw/                     run_plan.json, control_state.json, launch_*.log;
                           classification.json and literature_grounding.json for planned runs
  graphs/                  Tg fit and equation-of-state plots, when those stages ran
  attempts/<stage>/attempt-NNNN/
    executor_state.json    parameters in force, artifacts with sha256 and size, outputs
    raw/                   gate and analysis JSON for the stage
    work/                  LAMMPS input decks, launch scripts, logs and stdout
```

Stages are `build`, `equilibration`, `cooling`, `thermal`, `mechanical` and `summary`. Failed
attempts are kept next to the accepted one.

Paths recorded inside the files are absolute paths on the host that ran the job:
`/home/arz2/PolyJarvis_v2/data/` on the RTX 6000 host and `/home/alexzhao/...` on the A800 host.
The generators map them to this folder.

## Changes made after the runs finished

Each change is recorded in the run's `workflow_state.json` under `input_hash_restamp`. None of
them re-ran a simulation or an analysis:

- Trajectory dumps were compressed to `.dump.gz`, and the artifact checksums and dependent stage
  input hashes were updated to match.
- `aPS_1` and `sPVC_1` are locked-protocol reruns of replicate 1. They ran as `aPS_1_rerun` and
  `sPVC_1_rerun` and were renamed on 2026-09-16, after the original replicate-1 runs were deleted.
  The old name was replaced in every text file of the run, including the LAMMPS logs.
