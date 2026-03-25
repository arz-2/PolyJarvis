# PolyJarvis MCP Tools Reference
**Last updated:** March 25, 2026
**RadonPy server:** `/home/alexanderzhao/Desktop/Research/PolyJarvis/mcp-servers/mcp-radonpy-server/src/server.py`
**Lammps-Engine server:** `/home/alexanderzhao/Desktop/Research/PolyJarvis/mcp-servers/mcp-lammps-engine/server.py`

This file is the canonical reference for all available MCP tools. Stage files contain usage examples and workflow context. This file contains complete signatures, parameter descriptions, and return schemas.

**Two MCP servers are in use:**
- **RadonPy server** — molecular construction tools (Stage 1). Tools are called directly: `classify_polymer(...)`, `build_molecule_from_smiles(...)`, etc.
- **Lammps-Engine server** — simulation execution and analysis tools (Stages 2–4). Tools are prefixed: `lammps_engine.generate_script(...)`, `lammps_engine.run_lammps_script(...)`, etc.

---

## Quick Index

### RadonPy Server (molecular construction — Stage 1)

| Tool | Type | Stage | Purpose |
|---|---|---|---|
| `classify_polymer` | sync | 1 | Classify SMILES → PoLyInfo backbone class |
| `build_molecule_from_smiles` | sync | 1 | Build monomer from SMILES |
| `submit_conformer_search_job` | async | 1 | QM conformer search (Psi4) |
| `submit_assign_charges_job` | async | 1 | RESP/ESP charge assignment |
| `submit_polymerize_job` | async | 1 | Homopolymer chain construction |
| `submit_copolymerize_job` | async | 1 | Alternating copolymer (ABABAB…) |
| `submit_random_copolymerize_job` | async | 1 | Random/statistical copolymer |
| `submit_block_copolymerize_job` | async | 1 | Block copolymer (AAAn-BBBm) |
| `assign_forcefield` | sync | 1 | Assign FF parameters to polymer |
| `submit_generate_cell_job` | async | 1 | Single-component amorphous cell |
| `submit_generate_mixture_cell_job` | async | 1 | Multi-component amorphous cell (blends) |
| `save_molecule` | sync | 1 | Save mol to json/pdb/xyz/mol |
| `save_lammps_data` | sync | 1 | Export cell to LAMMPS .data file |
| `get_molecule_info` | sync | 1 | Inspect molecule properties |
| `submit_sp_properties_job` | async | 1 | QM single-point properties |
| `get_job_status` | sync | 1 | Poll RadonPy async job |
| `get_job_output` | sync | 1 | Retrieve RadonPy async job result |
| `list_all_jobs` | sync | 1 | List all RadonPy jobs |
| `cancel_job` | sync | 1 | Cancel pending/running RadonPy job |
| `get_job_logs` | sync | 1 | Retrieve RadonPy job log file |

### Lammps-Engine Server (simulation execution and analysis — Stages 2–4)

| Tool | Type | Stage | Purpose |
|---|---|---|---|
| `generate_script` | sync | 2/3 | Fill template → .in script, upload to Lambda |
| `generate_equilibration_workflow` | sync | 2 | Auto-generate full 5-stage equilibration workflow |
| `run_lammps_script` | async | 2/3 | Run single .in script on Lambda GPU |
| `run_lammps_chain` | async | 2/3 | Run ordered sequence of scripts as chained pipeline |
| `get_run_status` | sync | any | Poll lammps-engine async run |
| `get_run_output` | sync | any | Retrieve lammps-engine run result |
| `list_runs` | sync | any | List all lammps-engine runs |
| `parse_data_file` | sync | 2 | Parse .data file → atom types, H types, box dims |
| `get_template_defaults` | sync | 2 | Show default parameters for a template |
| `upload_file_to_remote` | sync | 2 | Upload local file to Lambda |
| `download_file_from_remote` | sync | 4 | Download file from Lambda to local |
| `execute_remote_shell_command` | sync | any | Run arbitrary shell command on Lambda |
| `check_remote_file_exists` | sync | any | Check if a file exists on Lambda |
| `check_remote_status` | sync | any | Get Lambda server status |
| `list_remote_files` | sync | any | List files in a remote directory |
| `list_remote_files_detailed` | sync | any | List files with sizes and timestamps |
| `read_remote_file` | sync | any | Read a remote file |
| `read_remote_file_tail` | sync | any | Read last N lines of a remote file |
| `read_remote_log` | sync | any | Read LAMMPS log with parsed thermo |
| `write_remote_file` | sync | any | Write content to a remote file |
| `check_equilibration` | async | 2/4 | Check density + energy convergence (drift + block tests) |
| `extract_tg` | async | 4 | Extract Tg from Tg-sweep log (F-stat + bilinear) |
| `extract_equilibrated_density` | async | 4 | Extract plateau density from NPT log |
| `extract_bulk_modulus` | async | 4 | Extract isothermal bulk modulus from NPT log |
| `extract_end_to_end_vectors` | async | 4 | Compute per-chain R from trajectory |
| `calculate_rdf` | async | 4 | Compute g(r) for atom-type pairs |
| `unwrap_coordinates` | async | 4 | Write image-flag unwrapped dump file |

---

## Tool Signatures

### `classify_polymer` *(sync)*
**Added:** Feb 26 2026 | **Updated:** Mar 9 2026 | **Call order:** Always first

Wraps `radonpy.core.poly.polyinfo_classifier` — extracts mainchain, builds a cyclic tetramer, runs SMARTS matching against 21 PoLyInfo backbone classes.

```python
classify_polymer(smiles: str) -> dict
```

| Param | Type | Description |
|---|---|---|
| `smiles` | str | Polymer SMILES with `*` or `[*]` attachment points |

**Returns:**
```python
{
    "status": "success" | "error",
    "class_id": int,              # 0–21; 0 = failed classification
    "class_name": str,            # e.g. "PHYC", "PSTR", "PACR"
    "description": str,           # Full class description e.g. "Polyhydrocarbon", "Polyacrylic"
    "flags": dict,                # All 21 group matches {class_name: bool}
    "co_occurring_groups": list,  # [{class_id, class_name, description}] for matched non-winners
    "warning": str | None,        # Known accuracy issue if any; log this in SUMMARY_LOG
    "message": str                # e.g. "Class 1 (PHYC): Polyhydrocarbon"
}
```

**Note:** FF, charge method, and electrostatics are NOT returned by this tool — those are agent decisions based on the returned class_id. See the class table in STAGE_1 for guidance.

**Class ID table:**

| ID | Name | Example polymers | FF | Notes |
|---|---|---|---|---|
| 0 | UNKNOWN | — | None | Bad SMILES; stop and fix |
| 1 | PHYC | PE, PP, PIB | GAFF2 | ⚠️ NOT GAFF2_mod; validated error ~80K Tg |
| 2 | PSTR | PS | GAFF2_mod | |
| 3 | PVNL | PVA, PAN | GAFF2_mod | |
| 4 | PACR | PMMA, PAA | GAFF2_mod | |
| 5 | PHAL | PTFE, PVC | GAFF2_mod | |
| 6 | PDIE | Polybutadiene, Polyisoprene | GAFF2_mod | ⚠️ Verify cis/trans SMILES |
| 7 | POXI | PEO, PPO | GAFF2_mod | |
| 8 | PSUL | Polythioether | GAFF2_mod | |
| 9 | PEST | PET, PLA, PCL | GAFF2_mod | |
| 10 | PAMD | Nylon-6, Nylon-66 | GAFF2_mod | |
| 11 | PURT | Polyurethane | GAFF2_mod | |
| 12 | PURA | Polyurea | GAFF2_mod | |
| 13 | PIMD | Kapton, PI | GAFF2_mod | |
| 14 | PANH | Polyanhydride | GAFF2_mod | |
| 15 | PCBN | PC | GAFF2_mod | |
| 16 | PIMN | Polyamine | GAFF2_mod | |
| 17 | PSIL | PDMS | GAFF2_mod | |
| 18 | PPHS | Polyphosphazene | GAFF2_mod | |
| 19 | PKTN | PEEK | GAFF2_mod | |
| 20 | PSFO | Polysulfone | GAFF2_mod | |
| 21 | PPNL | PPV | GAFF2_mod | |

---

### `build_molecule_from_smiles` *(sync)*

```python
build_molecule_from_smiles(smiles: str, add_hydrogens: bool = True) -> dict
```

**Returns:** `{"temp_file": str, "num_atoms": int, "num_bonds": int, "has_3d": bool}`

⚠️ `temp_file` path is reused across calls. Save to a named path immediately with `save_molecule()`.

---

### `submit_conformer_search_job` *(async)*

```python
submit_conformer_search_job(
    mol_file: str,
    ff: str = None,          # If None, uses MMFF94 via RDKit (fast). Set ff object for full QM.
    psi4_omp: int = 1,       # OpenMP threads for Psi4 (use this, NOT omp)
    mpi: int = 1,
    omp: int = 1,
    memory: int = 2000,      # MB for Psi4
    log_name: str = "monomer1",
    work_dir: str = "conformer_search"
) -> dict
```

Runtime: 1–2 hours. Skip for simple linear monomers (PE, PP).

---

### `submit_assign_charges_job` *(async)*

```python
submit_assign_charges_job(
    mol_file: str,
    charge_method: "gasteiger" | "RESP" | "ESP" | "Mulliken" | "Lowdin" = "RESP",
    optimize_geometry: bool = False,
    omp_psi4: int = 1,
    memory: int = 2000,
    work_dir: str = "assign_charges"
) -> dict
```

Runtime: 30 min–2 hours. Use RESP for polar polymers (POXI, PEST, PAMD, etc.), Gasteiger only for quick testing or nonpolar systems (PHYC).

---

### `submit_polymerize_job` *(async)*

```python
submit_polymerize_job(
    mol_file: str,
    degree_of_polymerization: int,
    tacticity: "isotactic" | "syndiotactic" | "atactic" = "atactic",
    headhead: bool = False
) -> dict
```

⚠️ Overwrites `mol_file` in place. Save monomer to a checkpoint path first.

**Tacticity guidance:**
- `atactic`: default, physically realistic for most amorphous polymers
- `isotactic`: use for PP (isotactic PP has Tm ~165°C vs atactic PP which is amorphous)
- `syndiotactic`: use for PS syndiotactic studies

---

### `submit_copolymerize_job` *(async)*
**Added:** Feb 26 2026

```python
submit_copolymerize_job(
    mol_files: List[str],               # Ordered monomer JSON paths defining repeating unit
    degree_of_polymerization: int,       # Number of full sequence repeats
    output_file: str,
    tacticity: "isotactic" | "syndiotactic" | "atactic" = "atactic"
) -> dict
```

Builds alternating copolymer: `mol_files=[A, B]`, `n=30` → (AB)₃₀, 60 total monomers.
Total atoms = n × sum(atoms per monomer in sequence).

**Do NOT assign force field to monomers before this step.**

---

### `submit_random_copolymerize_job` *(async)*
**Added:** Feb 26 2026

```python
submit_random_copolymerize_job(
    mol_files: List[str],
    ratio: List[float],                  # Mole fractions; auto-normalised, need not sum to 1
    degree_of_polymerization: int,       # Total monomer count
    output_file: str,
    tacticity: "isotactic" | "syndiotactic" | "atactic" = "atactic",
    ratio_type: "exact" | "choice" = "exact"
) -> dict
```

`ratio_type="exact"`: composition enforced precisely (rounds to nearest int). Use for production.
`ratio_type="choice"`: each monomer drawn probabilistically; can deviate on short chains.

**Do NOT assign force field to monomers before this step.**

---

### `submit_block_copolymerize_job` *(async)*
**Added:** Feb 26 2026

```python
submit_block_copolymerize_job(
    mol_files: List[str],        # One entry per block, in order
    block_lengths: List[int],    # Monomers per block; must be same length as mol_files
    output_file: str,
    tacticity: "isotactic" | "syndiotactic" | "atactic" = "atactic"
) -> dict
```

`mol_files=[A, B]`, `block_lengths=[40, 30]` → A₄₀-B₃₀ diblock.
ABA triblock: pass same monomer JSON path twice: `mol_files=[A, B, A]`, `block_lengths=[20, 30, 20]`.

**Do NOT assign force field to monomers before this step.**

---

### `assign_forcefield` *(sync)*

```python
assign_forcefield(
    mol_file: str,
    forcefield: "GAFF" | "GAFF2" | "GAFF2_mod" = "GAFF2_mod"
) -> dict
```

**Must be called AFTER polymerization.** Use GAFF2 for PHYC (hydrocarbons), GAFF2_mod for all other classes. See STAGE_1 class table.

Returns: `{"atom_types": list, "num_atom_types": int}`

---

### `submit_generate_cell_job` *(async)*

```python
submit_generate_cell_job(
    mol_file: str,           # Single FF-assigned polymer chain
    num_chains: int,
    density: float = 0.05,  # Always 0.05 — never higher at packing stage
    temperature: float = 300.0
) -> dict
```

| chains | ~atoms (100-mer) | Use for |
|---|---|---|
| 6 | ~12,000 | Fast screening |
| 10 | ~20,000 | Standard production |
| 20 | ~40,000 | Publication |

---

### `submit_generate_mixture_cell_job` *(async)*
**Added:** Feb 26 2026

```python
submit_generate_mixture_cell_job(
    mol_files: List[str],              # List of FF-assigned polymer chain JSONs
    chains_per_component: List[int],   # Chains per component; same length as mol_files
    output_file: str,
    density: float = 0.05,
    temperature: float = 300.0
) -> dict
```

Each `mol_file` must be a **fully polymerised + FF-assigned** chain (unlike copolymer tools which take monomers).

**Returns:**
```python
{
    "cell_type": "amorphous_mixture",
    "composition": [{"component": str, "n_chains": int, "fraction": float}, ...],
    "total_chains": int,
    "num_atoms": int,
    "density_actual_g_cm3": float,
    "cell_dimensions_angstrom": {"x": float, "y": float, "z": float},
    "cell_volume_angstrom3": float,
    "output_file": str
}
```

---

### `save_molecule` *(sync)*

```python
save_molecule(mol_file: str, output_path: str,
              format: "json" | "mol" | "pdb" | "xyz" | "lammps" = "json") -> dict
```

Use `format="json"` for checkpoints. `format="lammps"` requires FF assignment first.

---

### `save_lammps_data` *(sync)*

```python
save_lammps_data(
    mol_file: str,
    output_path: str,
    temp: float = 300.0,
    include_velocities: bool = True
) -> dict
```

Prerequisite: FF must be assigned. Writes the `.data` file for Lambda upload.

**Returns:** `{"num_atoms": int, "atom_types": list, "box": {"x","y","z"}, "density_g_cm3": float}`

---

### `get_molecule_info` *(sync)*

```python
get_molecule_info(mol_file: str) -> dict
```

Returns: `{"num_atoms", "has_charges", "has_forcefield", "is_cell", "density", "molecular_weight"}`

---

### `submit_sp_properties_job` *(async)*

```python
submit_sp_properties_job(
    mol_file: str,
    method: str = "HF",
    basis: str = "6-31G(d)",
    omp_psi4: int = 1,
    mem: int = 2000,
    work_dir: str = "sp_properties"
) -> dict
```

Returns HOMO, LUMO, total energy, dipole, polarizability.

---

### `check_equilibration` *(async — Lammps-Engine)*
**Added/renamed:** March 2026

Checks convergence by applying a drift test (linear regression) and a block-average test (Flyvbjerg-Petersen, JCP 1989) to both density and total energy. System is considered equilibrated only if both properties pass both tests.

```python
check_equilibration(
    log_file: str,
    output_dir: str = None,             # Defaults to <log_dir>/eq_analysis/
    eq_fraction: float = 0.5,           # Fraction of rows used as production window
    drift_threshold_pct: float = 1.0,   # Max allowed drift as % of mean
    drift_pvalue: float = 0.01,         # p-value threshold for drift significance
    block_count: int = 5,               # Blocks for block-average SEM test
    temp_col: str = "Temp",
    press_col: str = "Press",
    density_col: str = "Density",
    energy_col: str = "TotEng"
) -> dict   # Returns {run_id: str} — poll with get_run_status()
```

**Returns (on completion):**
```python
{
    "equilibrated": bool,              # True only if density AND energy both pass
    "density_equilibrated": bool,
    "energy_equilibrated": bool,
    "density": {
        "drift":     {"pass": bool, "slope": float, "p_value": float, "drift_pct": float},
        "block_avg": {"pass": bool, "sem": float, "sem_pct": float}
    },
    "energy": {
        "drift":     {"pass": bool, "slope": float, "p_value": float, "drift_pct": float},
        "block_avg": {"pass": bool, "sem": float, "sem_pct": float}
    },
    "meta": {
        "T_mean": float, "P_mean": float,
        "n_rows_total": int, "n_rows_production": int
    },
    "summary_json": str   # Path to JSON on Lambda
}
```

---

### RadonPy Job Management Tools *(all sync — RadonPy server)*

```python
get_job_status(job_id: str) -> {"status": "pending"|"running"|"completed"|"failed", ...}
get_job_output(job_id: str) -> {"result": dict, "output_files": list, ...}
list_all_jobs(status_filter: str = None) -> {"jobs": list}
cancel_job(job_id: str) -> {"message": str}
get_job_logs(job_id: str) -> {"log_content": list}
```

**Standard polling pattern (RadonPy):**
```python
job = submit_*_job(...)
while get_job_status(job["job_id"])["status"] not in ("completed", "failed"):
    time.sleep(30)
result = get_job_output(job["job_id"])
if result["status"] == "failed":
    raise RuntimeError(get_job_logs(job["job_id"])["log_content"][-10:])
```

---

## Input Compatibility Matrix

Which tools take monomers vs polymers vs cells:

| Tool | Input must be |
|---|---|
| `submit_conformer_search_job` | Monomer JSON (from `build_molecule_from_smiles`) |
| `submit_assign_charges_job` | Monomer JSON |
| `submit_polymerize_job` | Monomer JSON (with charges) |
| `submit_copolymerize_job` | List of monomer JSONs (with charges) |
| `submit_random_copolymerize_job` | List of monomer JSONs (with charges) |
| `submit_block_copolymerize_job` | List of monomer JSONs (with charges) |
| `assign_forcefield` | Polymer JSON (after polymerization) |
| `submit_generate_cell_job` | Polymer JSON (after FF assignment) |
| `submit_generate_mixture_cell_job` | List of polymer JSONs (each after FF assignment) |
| `save_lammps_data` | Cell JSON (after `submit_generate_*_cell_job`) |

---

## Tested Tool Coverage

### RadonPy Server

| Tool | Test status | Notes |
|---|---|---|
| `build_molecule_from_smiles` | ✅ Tested | Core tool, stable |
| `submit_polymerize_job` | ✅ Tested | Overwrites mol_file in place |
| `assign_forcefield` | ✅ Tested | |
| `save_molecule` | ✅ Tested | |
| `save_lammps_data` | ✅ Tested | |
| `get_molecule_info` | ✅ Tested | |
| `submit_generate_cell_job` | ✅ Tested | Extensively in PS production runs |
| `submit_copolymerize_job` | ✅ Tested Feb 26 | (EP)₅ → 77 atoms, Mn=356.7 |
| `submit_random_copolymerize_job` | ✅ Tested Feb 26 | 60/40 ratio exact mode works |
| `submit_block_copolymerize_job` | ✅ Tested Feb 26 | Diblock + ABA triblock both pass |
| `submit_generate_mixture_cell_job` | ✅ Tested Feb 26 | 2+2 chain blend, ρ=0.052 |
| `classify_polymer` | ✅ Tested Mar 9 | Wraps `poly.polyinfo_classifier`; 8/8 polymers correct |
| `submit_conformer_search_job` | ✅ Tested | Requires Psi4 |
| `submit_assign_charges_job` | ✅ Tested | Requires Psi4 |

### Lammps-Engine Server

| Tool | Test status | Notes |
|---|---|---|
| `generate_script` | ✅ Tested | All templates: minimize, nvt, npt, npt_compress, npt_tg_step, nemd_thermal |
| `run_lammps_script` | ✅ Tested | Nohup background; survives server restarts |
| `run_lammps_chain` | ✅ Tested | Full eq pipeline tested |
| `get_run_status` | ✅ Tested | Reads progress file live from Lambda |
| `get_run_output` | ✅ Tested | |
| `parse_data_file` | ✅ Tested | SHAKE H-type detection reliable |
| `check_equilibration` | ✅ Tested Mar 2026 | Drift + block-average; replaces `analyze_equilibration` |
| `extract_tg` | ✅ Tested Mar 2026 | v3 F-stat split; replaces scipy-only v2 |
| `extract_equilibrated_density` | ✅ Tested Mar 2026 | Reverse-cumulative-mean plateau detection |
| `extract_bulk_modulus` | ✅ Tested Mar 2026 | Volume-fluctuation method; requires NPT log |
| `extract_end_to_end_vectors` | ✅ Tested Mar 2026 | `backbone_types` now required; sort_backbone |
| `calculate_rdf` | ✅ Tested Mar 2026 | `data_file` now required; MDAnalysis InterRDF |
| `unwrap_coordinates` | ✅ Tested | |
| `execute_remote_shell_command` | ✅ Tested | Standard shell; timeout default 60s |
| `upload_file_to_remote` | ✅ Tested | Replaces `upload_file_to_lambda` |
| `download_file_from_remote` | ✅ Tested | Replaces `download_file_from_lambda` |

---

## Lammps-Engine Tool Signatures

### `generate_script` *(sync)*

```python
generate_script(
    template_name: str,         # "minimize" | "nvt" | "npt" | "npt_compress" | "npt_tg_step" | "nemd_thermal"
    data_file: str,             # Remote path to .data file on Lambda
    output_script: str,         # Local path to write the generated .in file
    params: dict,               # Parameter overrides (see get_template_defaults for options)
    upload_to_lambda: bool = True,
    remote_output_dir: str = None  # Defaults to dirname of data_file
) -> dict
```

**Returns:** `{"script_content": str, "local_path": str, "remote_path": str}`

Common `params` keys: `T_START`, `T_FINAL`, `N_STEPS`, `T_DAMP`, `P_START`, `P_FINAL`, `P_DAMP`, `use_gpu`, `LOG_FILE`, `DUMP_FILE`

---

### `generate_equilibration_workflow` *(sync)*

Auto-generates a complete 5-stage equilibration workflow (minimize → npt_compress → nvt → npt → nvt_production).

```python
generate_equilibration_workflow(
    data_file: str,          # Remote path to .data file on Lambda
    work_dir_base: str,      # Remote base directory for all stages
    polymer_name: str = "polymer",
    temp: float = 300,       # Target simulation temperature (K)
    max_temp: float = 600,   # Peak annealing temperature (K); typically ~2× Tg
    press: float = 1,        # Target pressure (atm)
    max_press: float = 50000,  # Compression pressure (atm)
    n_chains: int = 6,
    n_atoms: int = None      # Auto-detected from data file if not provided
) -> dict
```

**Returns:** `{"stages": list, "run_order": list, "instructions": str}`

---

### `run_lammps_script` *(async)*

```python
run_lammps_script(
    remote_script: str,       # Full path to .in file on Lambda
    remote_work_dir: str,     # Working directory for outputs
    log_file: str = "lammps_run.log",
    mpi: int = 2,             # MPI processes = number of GPUs
    gpu_ids: str = "0,1"      # Comma-separated GPU IDs — always set explicitly
) -> dict                     # Returns {run_id: str}
```

**MPI/GPU guidance:**
| System atoms | MPI | Notes |
|---|---|---|
| < 5k | 1 | Single GPU sufficient |
| 5–10k | 2 | Standard |
| > 10k / Tg sweeps | 4 | Use all free GPUs |

---

### `run_lammps_chain` *(async)*

Executes a sequence of scripts as a nohup pipeline. Each stage runs to completion before the next starts. The chain survives MCP server restarts and disconnections.

```python
run_lammps_chain(
    stages: list,    # Ordered list of {name, remote_script, remote_work_dir, log_file}
    mpi: int = 2,
    gpu_ids: str = "0,1"
) -> dict            # Returns {chain_id: str}
```

Poll with `get_run_status(chain_id)`.

---

### `get_run_status` / `get_run_output` / `list_runs` *(all sync)*

```python
get_run_status(run_id: str) -> {"status": "pending"|"running"|"completed"|"failed", ...}
get_run_output(run_id: str) -> {"result": dict, "log_tail": list, "output_files": list}
list_runs(status_filter: str = None) -> list
```

**Standard polling pattern (Lammps-Engine):**
```python
run = run_lammps_script(...)   # or extract_tg, calculate_rdf, etc.
while get_run_status(run["run_id"])["status"] not in ("completed", "failed"):
    time.sleep(30)
result = get_run_output(run["run_id"])["result"]
```

---

### `parse_data_file` *(sync)*

```python
parse_data_file(
    data_file: str,
    remote: bool = True   # If True, reads from Lambda via SSH
) -> dict
```

**Returns:** `{n_atoms, n_atom_types, box dimensions, atom type names/masses, h_type_ids, estimated_memory}`

Use `h_type_ids` for SHAKE constraints. Use atom type IDs for `backbone_types` in `extract_end_to_end_vectors` and `atom_type_pairs` in `calculate_rdf`.

---

### `upload_file_to_remote` / `download_file_from_remote` *(sync)*

```python
upload_file_to_remote(local_path: str, remote_path: str = None) -> dict
download_file_from_remote(remote_path: str, local_path: str = None) -> dict
```

`remote_path` defaults to `/home/arz2/simulations/<filename>` if not set.
`local_path` defaults to `/tmp/<filename>` if not set.

---

### `execute_remote_shell_command` *(sync)*

```python
execute_remote_shell_command(
    command: str,
    workdir: str = None,  # Defaults to remote_workdir
    timeout: int = 60
) -> {"stdout": str, "stderr": str, "exit_code": int}
```

---

### Remote File Tools *(all sync)*

```python
check_remote_file_exists(remote_path: str) -> {"exists": bool}
check_remote_status() -> dict   # Lambda server status
list_remote_files(remote_dir: str) -> list
list_remote_files_detailed(remote_dir: str) -> list  # With sizes and timestamps
read_remote_file(remote_path: str) -> {"content": str}
read_remote_file_tail(remote_path: str, n_lines: int = 50) -> {"lines": list}
read_remote_log(remote_log_path: str = None, run_id: str = None, n_lines: int = 100) -> dict
write_remote_file(remote_path: str, content: str) -> dict
```

`read_remote_log` accepts either a file path or a `run_id` (uses the run's log path automatically).
