# PolyJarvis MCP Tools Reference
**Last updated:** May 29, 2026

Quick index of all available MCP tools.

**Three MCP servers:**
- **Mol-Builder server** (`mcp-mol-builder-server`) — molecular construction (Stage 1, RadonPy/GAFF2_mod path for PURA only)
- **EMC server** (`mcp-emc-server`) — amorphous cell builder for PCFF, OPLS-AA, and TraPPE-UA (Stage 1, 20 of 21 classes)
- **LAMMPS Engine server** (`mcp-lammps-engine`) — simulation execution and analysis (Stages 2–4)

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
| `submit_generate_cell_job` | async | Single-component amorphous cell |
| `submit_generate_copolymer_cell_job` | async | Multi-chain copolymer amorphous cell |
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


**SMILES conventions (critical):**
- PCBN: full carbonate `-O-C(=O)-O-` in repeat unit; `*` on aromatic C
- PAMD: amide N adjacent to C=O (not split across `*`)
- PIMD: all imide ring atoms lowercase for sp2 `npc` type; uppercase N → crash
- PDIE: cis/trans microstructure in SMILES; `*C/C=C\C*` for cis-PBD
- PSTR/PHYC: tacticity only via `[C@@H]`/`[C@H]` with OPLS-AA; **not** with TraPPE-UA (UA has no explicit H)

---

## LAMMPS Engine Server

### Simulation

| Tool | Type | Purpose |
|---|---|---|
| `list_templates` | sync | All templates; pass `template_name` for defaults |
| `inspect_data_file` | sync | Parse + validate in one call: atom count, box dims, H-type IDs, pre-flight checks |
| `generate_script` | sync | Fill template → write `.in` file; `use_pcff=True` for PCFF class2 |
| `generate_equilibration_workflow` | sync | Auto-generate 7-stage GPU equilibration; `use_pcff=True` for PCFF; `params_file=` for EMC builds |
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
| `extract_tg` | async | Tg from sweep log via F-stat bilinear fit |
| `extract_bulk_modulus` | async | Isothermal K from NPT volume fluctuations |
| `extract_end_to_end_vectors` | async | Per-chain R vectors |
| `calculate_rdf` | async | g(r) for atom-type pairs |
| `unwrap_coordinates` | async | Image-flag-unwrapped dump file |

---

## Input Compatibility

| Tool | Input must be |
|---|---|
| `submit_conformer_search_job` | Monomer JSON |
| `submit_assign_charges_job` | Monomer JSON |
| `submit_polymerize_job` | Monomer JSON (with charges) |
| `submit_copolymerize_job` | List of monomer JSONs (with charges) |
| `assign_forcefield` | Polymer JSON (after polymerization) |
| `submit_generate_cell_job` | Polymer JSON (after FF assignment) |
| `submit_generate_copolymer_cell_job` | List of polymer JSONs (after FF assignment) |
| `save_lammps_data` | Cell JSON (after `submit_generate_*_cell_job`) |

