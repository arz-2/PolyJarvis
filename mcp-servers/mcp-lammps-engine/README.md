# PolyJarvis LAMMPS Engine

Template-based LAMMPS script generation, remote execution, and post-simulation analysis MCP server for polymer MD simulations. Handles the downstream half of the PolyJarvis pipeline: `.data` file → simulation → property extraction.

## Architecture

```
RadonPy Server (upstream)              PolyJarvis LAMMPS Engine (this server)
──────────────────────────             ────────────────────────────────────────────────────
SMILES → polymer chain                 .data file
  → amorphous cell         →           → parse_data_file()               reads system info
  → .data file             →           → generate_script()               fills template
                                       → run_lammps_script()             executes remotely
                                       → get_run_status()                polls progress
                                       → read_remote_log()               live monitoring
                                       ─ Analysis ────────────────────────────────────────
                                       → check_equilibration()           convergence check
                                       → extract_equilibrated_density()  plateau density
                                       → extract_tg()                    glass transition T
                                       → extract_bulk_modulus()          isothermal K
                                       → unwrap_coordinates()            image-flag unwrap
                                       → extract_end_to_end_vectors()    chain R vectors
                                       → calculate_rdf()                 g(r)
```

## File Structure

```
mcp-lammps-engine/
├── server.py              # MCP server (18 tools)
├── utilities.py           # Remote utility tools (10 tools, registered at startup)
├── script_generator.py    # Data file parser + template filler
├── remote_executor.py     # SSH/SFTP executor (copied from RadonPy server)
├── templates/
│   ├── minimize.in
│   ├── nvt.in
│   ├── npt.in
│   ├── npt_compress.in
│   ├── npt_tg_step.in
│   ├── nemd_thermal.in
│   ├── nemd_supercell.in
│   ├── nemd_langevin.in
│   └── nemd_shear.in
└── README.md
```

## Templates

| Template | Use Case | GPU Safe? | Restarts? |
|---|---|---|---|
| `minimize` | Relax bad contacts in fresh amorphous cell | CPU | No |
| `nvt` | Heating ramps, constant-T annealing, production | ✅ Yes | Optional |
| `npt` | Density equilibration | CPU (with restart) | Yes |
| `npt_compress` | Low→target density compression (lj/cut only) | CPU | Yes |
| `npt_tg_step` | Single T point in Tg sweep | ✅ Yes | No |
| `nemd_thermal` | Thermal conductivity — Muller-Plathe | CPU | No |
| `nemd_supercell` | Muller-Plathe on pre-replicated supercell | CPU | No |
| `nemd_langevin` | Direct Langevin thermostat thermal conductivity | CPU | No |
| `nemd_shear` | SLLOD shear viscosity | CPU | No |

**GPU + restart rule:** NPT stages run on CPU (LAMMPS restart files corrupt under GPU + NPT). NVT production stages run on GPU. `npt_tg_step` is restart-free by design so GPU is safe there.

## Typical Equilibration Workflow

```python
generate_equilibration_workflow(
    data_file="/home/arz2/simulations/my_polymer/cell.data",
    work_dir_base="/home/arz2/simulations/my_polymer/eq",
    polymer_name="polystyrene",
    temp=300.0,
    max_temp=600.0,
)
```

Auto-generates 6 chained scripts executed in order:

1. `01_minimize`        — relax bad contacts
2. `02_nvt_softheat`    — heat to `max_temp` with lj/cut
3. `03_npt_compress`    — compress to target density with lj/cut
4. `04_npt_pppm`        — re-equilibrate with full PPPM (CPU)
5. `05_npt_cool`        — cool to target T (CPU, checkpointed)
6. `06_nvt_production`  — GPU NVT production for property extraction

## Analysis Tools

All analysis jobs submit to the remote server in the background. Poll progress with `get_run_status(run_id)`.

### `check_equilibration(log_file)`
Two-test convergence check on density and total energy over the production window (`eq_fraction`):
1. **Drift test** — linear regression; fails if drift > `drift_threshold_pct`% with p < `drift_pvalue`
2. **Block-average test** — Flyvbjerg & Petersen (JCP 1989); fails if block SEM > 1% of mean

### `extract_equilibrated_density(log_file)`
Reverse-cumulative-mean plateau detection: extends backwards from the last row, stopping when the cumulative mean shifts by > `plateau_shift_sigma` × SEM. Returns `plateau_density_mean ± plateau_density_sem` and a naive mean for sanity-checking.

### `extract_tg(log_file)` — v3, March 2026
Plateau detection bins each temperature set-point into one (T, ρ) point after equilibration burn-in. Plateaus with density drift > 1% (p < 0.01) are excluded. Fitting uses exhaustive F-stat split across all candidate breakpoints, with physics constraints (both slopes negative, rubbery steeper). Tg = bilinear intersection. Cross-validated against `scipy.optimize.curve_fit`. Quality rated by both R² and F-stat p-value.

References: Patrone et al., *Polymer* 87 (2016) 246–259 · Suter et al., *JCTC* 21 (2025) 1405–1421

### `extract_bulk_modulus(log_file)`
Volume fluctuation method (Allen & Tildesley, 2017): `K_T = kB·T·⟨V⟩/Var(V)`. Requires a well-equilibrated NPT run. Block averaging gives the SEM; includes a drift warning if equilibration is incomplete.

### `unwrap_coordinates(dump_file)`
Applies image-flag unwrapping (`x_unwrap = x + ix·Lx`) to every frame and writes a new dump file. All non-coordinate columns pass through unchanged.

### `extract_end_to_end_vectors(dump_file, data_file, backbone_types)`
MDAnalysis + `sort_backbone()` — traces the backbone bond graph to identify chain termini, then computes per-chain R vectors and distances across all frames. Returns per-chain mean/std R and R², plus a CSV.

### `calculate_rdf(dump_file, data_file)`
MDAnalysis InterRDF — standard g(r) normalised by ideal gas shell volume. One CSV per atom-type pair.

## MCP Tools Reference

### Simulation

| Tool | Description |
|---|---|
| `list_templates()` | Show all templates + one-line descriptions |
| `get_template_defaults(template_name)` | All tunable parameters with defaults |
| `parse_data_file(data_file, remote)` | Extract atom count, box, force-field info from `.data` file |
| `generate_script(template_name, data_file, output_script, params, upload_to_remote)` | Fill template and write `.in` file |
| `run_lammps_script(remote_script, remote_work_dir, mpi, gpu_ids)` | Submit single script |
| `run_lammps_chain(stages, ...)` | Submit ordered chain; runs under nohup, survives MCP restarts |
| `generate_equilibration_workflow(...)` | Auto-generate full 6-stage equilibration protocol |

### Monitoring

| Tool | Description |
|---|---|
| `get_run_status(run_id)` | Poll status of any run or analysis job |
| `get_run_output(run_id)` | Full result + last 100 lines of LAMMPS log |
| `list_runs(status_filter)` | All submitted runs and analysis jobs |
| `read_remote_log(run_id, n_lines)` | Live tail of LAMMPS log during a running job |

### Analysis

| Tool | Description |
|---|---|
| `check_equilibration(log_file)` | Drift + block-average convergence on density and energy |
| `extract_equilibrated_density(log_file)` | Plateau density via reverse-cumulative-mean |
| `extract_tg(log_file)` | Tg via exhaustive F-stat bilinear fit |
| `extract_bulk_modulus(log_file)` | Isothermal K via NPT volume fluctuations |
| `unwrap_coordinates(dump_file)` | Write new dump with image-flag-unwrapped coordinates |
| `extract_end_to_end_vectors(dump_file, data_file, backbone_types)` | Chain R vectors via MDAnalysis |
| `calculate_rdf(dump_file, data_file)` | g(r) via MDAnalysis InterRDF |

### Remote Utilities

| Tool | Description |
|---|---|
| `check_remote_status()` | Server connectivity, hostname, GPU availability |
| `list_remote_files(remote_dir)` | List files in a remote directory |
| `list_remote_files_detailed(remote_dir)` | List with size and modification time |
| `read_remote_file(remote_path)` | Read full content of a remote file |
| `read_remote_file_tail(remote_path, n_lines)` | Last N lines (log monitoring) |
| `write_remote_file(remote_path, content)` | Write or overwrite a remote file |
| `upload_file_to_remote(local_path, remote_path)` | Upload a local file |
| `download_file_from_remote(remote_path, local_path)` | Download to local |
| `execute_remote_shell_command(command, workdir, timeout)` | Run arbitrary shell command |
| `check_remote_file_exists(remote_path)` | Check whether a remote path exists |
