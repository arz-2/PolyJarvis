# PolyJarvis MCP Tools Reference
**Last updated:** July 6, 2026

Quick index of all available MCP tools.

**Three MCP servers:**
- **Mol-Builder server** (`mcp-mol-builder-server`)
- **EMC server** (`mcp-emc-server`)
- **LAMMPS Engine server** (`mcp-lammps-engine`)

---

## Mol-Builder Server

| Tool | Type | Purpose |
|---|---|---|
| `classify_polymer` | sync | Classify SMILES → PoLyInfo class; returns preferred FF and builder |
| `build_molecule_from_smiles` | sync | Build monomer from SMILES |
| `submit_conformer_search_job` | async | QM conformer search (Psi4) |
| `submit_assign_charges_job` | async | RESP / AM1-BCC / ESP / Gasteiger charge assignment |
| `submit_polymerize_job` | async | Homopolymer chain construction |
| `submit_copolymerize_job` | async | Copolymer chain construction (alternating/random/block) |
| `assign_forcefield` | sync | Assign GAFF2_mod parameters to PURA polymer chain (RadonPy path only) |
| `submit_generate_cell_job` | async | Single-component amorphous cell (homopolymer) |
| `submit_generate_copolymer_cell_job` | async | Multi-chain copolymer amorphous cell; input: list of polymer JSONs after FF assignment |
| `save_molecule` | sync | Save mol to json/pdb/xyz/mol |
| `save_lammps_data` | sync | Export cell to LAMMPS .data file |
| `get_molecule_info` | sync | Inspect molecule properties |
| `get_job_status` | sync | Poll RadonPy async job |
| `get_job_output` | sync | Retrieve RadonPy async job result |
| `list_all_jobs` | sync | List all RadonPy jobs |
| `cancel_job` | sync | Cancel pending/running RadonPy job |

---

## EMC Server

| Tool | Type | Purpose |
|---|---|---|
| `submit_emc_cell_job` | async | Build amorphous cell from SMILES; FF auto-selected from `polymer_class`; returns job_id |
| `get_emc_job_status` | sync | Poll EMC build job |
| `get_emc_job_output` | sync | Retrieve result; `data_path` = LAMMPS `.data` file; `lammps_flags` = `{use_pcff, use_opls}` |
| `list_emc_jobs` | sync | List all EMC jobs with status |

---

## LAMMPS Engine Server

### Simulation

| Tool | Type | Purpose |
|---|---|---|
| `list_templates` | sync | All templates when called with no args; pass `template_name` to get full parameter defaults for that template (replaces the old `get_template_defaults` — used by deform-worker, tg-sweep-worker before `generate_script`) |
| `inspect_data_file` | sync | Parse + validate in one call: atom count, box dims, H-type IDs, pre-flight checks |
| `generate_script` | sync | Fill template → write `.in` file; `use_pcff=True` for PCFF class2 |
| `generate_equilibration_workflow` | sync | Auto-generate 7-run (rubbery) or 9-run (glassy) GPU equilibration chain; `use_pcff=True` for PCFF; `params_file=` for EMC builds |
| `run_lammps_script` | async | Run single script (daemon thread) |
| `run_lammps_chain` | async | Run ordered pipeline under nohup; crash-safe |

### Monitoring

| Tool | Type | Purpose |
|---|---|---|
| `get_run_status` | sync | Poll run or chain status |
| `get_run_output` | sync | Full result + last 100 log lines |
| `list_runs` | sync | All submitted runs |
| `watch_run` | sync | Return Monitor command for auto-continuation |

### Analysis

| Tool | Type | Purpose |
|---|---|---|
| `check_equilibration_comprehensive` | async | All checks in one call: thermo drift+SEM, Rg CV, MSID, C(t), MSD, P2, density homogeneity — returns `overall_pass` + D-05 markdown |
| `extract_equilibrated_density` | async | Plateau density from NPT log |
| `extract_thermal` | async | Tg, CTE (α_g, α_r), ΔCp from sweep log via bilinear density + enthalpy fits; optional structural diagnostics from per-T dump |
| `extract_tg_multirate` | sync | Rate-extrapolated Tg from multiple cooling-rate runs; returns log-linear slope and VF Tg⁰ |
| `extract_bulk_modulus` | async | Isothermal K from NPT volume fluctuations (cross-check; rubbery no-pressures fallback) |
| `extract_bulk_modulus_murnaghan` | sync | Fits Murnaghan EOS to P vs V from a pressure series; returns B0, B0', V0 (primary K path — glassy 300 K and rubbery T>Tg) |
| `run_bulk_modulus_series` | async | Submits N NPT runs at each pressure in `pressures_atm`; returns chain_id + log_files list (used by murnaghan-worker) |
| `extract_bulk_modulus_deform` | sync | Young's modulus and K from a 3-direction uniaxial deformation log; fallback when a Murnaghan fit fails acceptance |
| `assess_cooling_contraction` | async | Volumetric contraction sanity check across the equilibration cooling stage |
| `generate_run_summary` | sync | Assembles `run_summary.json` with all properties, validation status, and experimental comparison; call after all analysis tools complete |
| `extract_end_to_end_vectors` | async | Per-chain R vectors |
| `calculate_rdf` | async | g(r) for atom-type pairs |
| `unwrap_coordinates` | async | Image-flag-unwrapped dump file |




