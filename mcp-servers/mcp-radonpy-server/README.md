# PolyJarvis RadonPy Server

Local MCP server for polymer structure building using [RadonPy](https://github.com/RadonPy/RadonPy). Handles the upstream half of the PolyJarvis pipeline: SMILES → force-fielded polymer chain → amorphous cell → LAMMPS `.data` file.

All heavy operations (conformer search, charge assignment, cell generation) run as background jobs so MCP tool calls return immediately.

## Architecture

```
RadonPy Server (this)                    LAMMPS Engine Server
─────────────────────────────────────    ─────────────────────────────────
SMILES
  → build_molecule_from_smiles()
  → assign_forcefield()
  → submit_conformer_search_job()
  → submit_assign_charges_job()
  → submit_polymerize_job()
  → submit_generate_cell_job()
  → save_lammps_data()             →     .data file → simulation & analysis
```

## Pipeline (typical order)

```python
# 1. Build molecule
build_molecule_from_smiles(smiles="CCO", add_hydrogens=True)
# → saves mol.json locally

# 2. Assign GAFF2 force field
assign_forcefield(mol_file="mol.json", ff="GAFF2_mod")

# 3. Conformer search (background)
job_id = submit_conformer_search_job(mol_file="mol.json")
# → poll with get_job_status(job_id)

# 4. Assign RESP charges (background)
job_id = submit_assign_charges_job(mol_file="mol_conf.json")

# 5. Polymerize
job_id = submit_polymerize_job(mol_file="mol_charged.json", degree_of_polymerization=10)

# 6. Build amorphous cell (background)
job_id = submit_generate_cell_job(mol_file="polymer.json", num_chains=5, density=0.8)

# 7. Save as LAMMPS data file
save_lammps_data(mol_file="cell.json", output_path="cell.data")
```

## File Structure

```
mcp-radonpy-server/
└── src/
    ├── server.py                   # MCP server (18 tools)
    ├── analysis_scripts/           # Python scripts executed on remote server
    │   ├── check_equilibration.py
    │   ├── extract_bulk_modulus.py
    │   ├── extract_equilibrated_density.py
    │   ├── extract_tg.py
    │   └── unwrap_dump.py
    ├── bashrc                      # Shell config for remote sessions
    └── timer.dat                   # Internal timing state
```

> **Note:** `analysis_scripts/` contains the scripts that the LAMMPS Engine server uploads to and runs on the remote simulation server. They live here as the canonical source but are deployed remotely at `/home/arz2/simulations/analysis_scripts/`.

## MCP Tools Reference

### Molecule building

| Tool | Description |
|---|---|
| `build_molecule_from_smiles(smiles)` | Parse SMILES, add hydrogens, save mol object |
| `classify_polymer(smiles)` | Identify polymer class and backbone from SMILES |
| `assign_forcefield(mol_file, ff)` | Assign GAFF2/GAFF2_mod parameters |
| `get_molecule_info(mol_file)` | Atom count, MW, charge, element breakdown |

### Background jobs (all return `job_id`)

| Tool | Description |
|---|---|
| `submit_conformer_search_job(mol_file)` | RDKit conformer search + geometry optimisation |
| `submit_assign_charges_job(mol_file)` | RESP charge assignment (Psi4 or AM1-BCC fallback) |
| `submit_sp_properties_job(mol_file)` | Single-point QM properties (HOMO, LUMO, dipole) |
| `submit_polymerize_job(mol_file, degree_of_polymerization)` | Build polymer chain |
| `submit_generate_cell_job(mol_file, num_chains, density)` | Pack amorphous simulation cell |

### Job management

| Tool | Description |
|---|---|
| `get_job_status(job_id)` | Poll status: pending / running / completed / failed |
| `get_job_output(job_id)` | Full result dict when completed |
| `list_all_jobs(status_filter)` | List all submitted jobs |
| `cancel_job(job_id)` | Cancel a pending or running job |
| `get_job_logs(job_id)` | Retrieve stdout/stderr logs for a job |
| `list_job_logs()` | List all available job log files |
| `get_logging_info()` | Current logging configuration |

### File output

| Tool | Description |
|---|---|
| `save_molecule(mol_file, output_path, format)` | Save mol in json/pickle/pdb/xyz/mol format |
| `save_lammps_data(mol_file, output_path)` | Write LAMMPS `.data` file (topology + force field) |
| `analyze_equilibration(...)` | Local equilibration analysis (density, energy) |
