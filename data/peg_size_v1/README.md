# PEG system-size pair (earlier-protocol cells)

The chain-count test quoted in SI Section S4 (bulk-modulus robustness): doubling the number of
chains in a rubbery COMPASS PEG cell changes the Murnaghan bulk modulus by +0.5%.

| Run | Field | Chains × DP | Atoms | ρ at 300 K (g/cm³) | B0 (GPa) | R² |
|---|---|---|---|---|---|---|
| `PEGCMP1` | COMPASS | 10 × 100 | 7,020 | 1.1241 | 2.740 ± 0.184 | 0.99973 |
| `PEG2XCMP1` | COMPASS | 20 × 100 | 14,040 | 1.1256 | 2.753 ± 0.094 | 0.99993 |

Values are from each run's `raw/equilibrated_density.json` and `raw/bulk_modulus_murnaghan.json`;
`manuscript/gen/collect_runs.py` reads them into `gen/out/runs.json`. The two
`lammps/cell/emc_build.esh` files differ in one line only: `poly alternate 10` → `20`.
Pressure ladder: −1000, 0, 3000, 7000 and 15000 atm at 300 K.

## Why these look different from the campaign runs

Both runs were made in August 2026 with the earlier checkout of PolyJarvis (stage-worker
architecture), before the deterministic control plane that produced the 21 campaign runs. They are
kept in that checkout's layout rather than reshaped into `attempts/`, since that would mean
writing run state they never had:

- `raw/`: run plan, density and Murnaghan fits, and `eq_armed/` with the equilibration check output
- `lammps/cell/`: EMC build script, parameters and log
- `lammps/equil/`: LAMMPS input and log per equilibration step. In `PEG2XCMP1`,
  `npt_pppm/crashed_attempt*/` keeps the logs of the two attempts that crashed before the one
  that completed
- `lammps/mechanical/bm_series/`: one directory per pressure point
- `PEGCMP1/run_log.md` and `PEGCMP1/eqcheck_prompt.txt`: the run log and the prompt given to the
  equilibration-check worker

Paths inside the files point to `/home/arz2/PolyJarvis/data/<run>/`, where the runs were made.
Trajectories, LAMMPS data files and restart files are not in the repository.
