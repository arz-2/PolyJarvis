# LAMMPS Error Taxonomy

| Error string in log | Root cause | Action |
|---|---|---|
| "lost atoms" | Timestep too large or bad starting geometry | Re-spawn with `--dt_fs 0.5`; verify data file with `inspect_data_file` |
| "out of memory" / GPU OOM | Cell too large for available VRAM | Reduce `--mpi_ranks`; use more GPU IDs |
| Segfault / "unknown atom type" | FF assigned before polymerization (RadonPy) | Re-run Stage 1 from `assign_forcefield` step |
| Energy NaN / diverges in first 100 steps | Bad initial config or density_initial too high | Re-spawn `--stage build` with `--density_initial` = class default − 0.10 g/cm³ |

`run_lammps_chain` crash: call `get_run_output(run_id)` to read the last error, then diagnose with the table above.
