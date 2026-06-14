# Stage 1: Molecular Construction
**Read when:** You have a SMILES string and need to produce a LAMMPS `.data` file  
**Worker:** molecule-builder — return RESULT block to orchestrator when done

---

## Path Routing

```
classify_polymer(smiles)
  ├─ PCBN/PAMD/PKTN/PSFO/PIMD/POXI/PEST/PSUL/PURT/PANH/PPHS/PACR/PIMN/PVNL/PPNL  →  Path A — EMC (pcff)
  ├─ PHAL, PSIL                →  Path A — EMC (opls/2024/opls-aa)
  ├─ PHYC, PDIE                 →  Path A — EMC (trappe-ua)
  └─ PURA                      →  Path B — RadonPy (GAFF2_mod + QM charges)
```

---

## Rule 0: classify_polymer is Always First

Call `classify_polymer(smiles)` before anything else. The returned `class_name` determines which path to follow.

- `class_id == 0` (UNKNOWN): stop — SMILES is malformed or missing `*` attachment points
- `warning` not None: log in run_log.md
- `co_occurring_groups` non-empty: note in run_log.md (no action required, affects uncertainty)

---

## Path A — EMC (20 classes)

EMC builds the amorphous cell and assigns all FF parameters in one step — no conformer search, charge assignment, polymerization, or FF assignment needed. The force field is selected automatically from `polymer_class`; do not pass a `field` argument.

### Class and FF Reference

| class_id | class_name | Description | Example polymers | FF | Electrostatics |
|---|---|---|---|---|---|
| 0 | UNKNOWN | Unclassified | Bad SMILES | ❌ Stop | — |
| 1 | PHYC | Polyhydrocarbon | PE, PP, PIB | TraPPE-UA | lj/cut |
| 2 | PSTR | Polystyrenic | PS, P2VP | PCFF | pppm |
| 3 | PVNL | Polyvinyl | PVA, PVC | PCFF | pppm |
| 4 | PACR | Polyacrylic | PMMA, PAA | PCFF | pppm |
| 5 | PHAL | Polyhalogenated | PVDF, PTFE | OPLS-AA | pppm |
| 6 | PDIE | Polydiene | PBD, PI | TraPPE-UA | lj/cut |
| 7 | POXI | Polyoxide/Polyether | PEO, PPO | PCFF | pppm |
| 8 | PSUL | Polythioether | PPS | PCFF | pppm |
| 9 | PEST | Polyester | PET, PLA | PCFF | pppm |
| 10 | PAMD | Polyamide | Nylon-6 | PCFF | pppm |
| 11 | PURT | Polyurethane | PU ⚠ | PCFF | pppm |
| 13 | PIMD | Polyimide | Kapton | PCFF | pppm |
| 14 | PANH | Polyanhydride | Polyanhydride | PCFF | pppm |
| 15 | PCBN | Polycarbonate | BPA-PC | PCFF | pppm |
| 16 | PIMN | Polyamine | PEI, epoxy | PCFF | pppm |
| 17 | PSIL | Polysiloxane | PDMS | OPLS-AA | pppm |
| 18 | PPHS | Polyphosphazene | Polyphosphazene | PCFF ⚠️ | pppm |
| 19 | PKTN | Polyketone/PEEK | PEEK | PCFF | pppm |
| 20 | PSFO | Polysulfone | PSU | PCFF | pppm |
| 21 | PPNL | Conjugated | PPV | PCFF | pppm |

⚠️ PPHS: PCFF has P=N backbone types but no polyphosphazene-specific validation. Low confidence — flag results.  
⚠ PURT: EMC aliphatic segments only; aromatic MDI fails.  
*PURA (class 12) routes to Path B — not listed here.*

### SMILES Conventions

| class_name | FF | Polymer | Correct SMILES | Note |
|---|---|---|---|---|
| PCBN | pcff | BPA-PC | `*OC(=O)Oc1ccc(C(C)(C)c2ccc(*)cc2)cc1` | Full carbonate in repeat unit; `*` on aromatic C |
| PAMD | pcff | Nylon-6 | `*C(=O)NCCCCC*` | Amide N must be adjacent to C=O; wrong placement → `{c_1, na}` error |
| PKTN | pcff | PEEK | `*Oc1ccc(Oc2ccc(C(=O)c3ccc(*)cc3)cc2)cc1` | — |
| PSFO | pcff | PSU (Udel) | `*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1` | — |
| PIMD | pcff | Kapton | `*c1ccc(n2c(=O)c3cc4c(cc3c2=O)c(=O)n(c5ccc(Oc6ccc(*)cc6)cc5)c4=O)cc1` | All imide ring atoms lowercase; uppercase N → `{na, c_1}` error |
| PHAL | opls-aa | PVDF | `*CC(F)(F)*` | — |
| PHAL | opls-aa | PTFE | `*C(F)(F)C(F)(F)*` | — |
| PHYC | trappe-ua | PE | `*CC*` | — |
| PHYC | trappe-ua | PP (atactic) | `*CC(C)*` | No chirality → atactic; use `*[C@@H](C)C*` for isotactic |
| PDIE | trappe-ua | cis-PBD | `*C/C=C\C*` | cis/trans microstructure must be encoded in SMILES |
| PSTR | pcff | PS (atactic) | `*CC(c1ccccc1)*` | No chirality → atactic |

> **PCBN:** The carbonate group (`-O-C(=O)-O-`) must be fully contained within the repeat unit. Placing `*` on the carbonyl oxygen causes `oz`/`oo` PCFF templates to fail silently — EMC exits with "Missing force field parameters."

> **PIMD:** All imide ring atoms must be lowercase (aromatic notation), including carbonyl carbons. Uppercase `N` → EMC assigns sp3 `na` type → no `c_1` increment pair.

> **TraPPE-UA tacticity:** `[C@@H]`/`[C@H]` chirality notation works with OPLS-AA but not TraPPE-UA (united-atom has no explicit H). For PHYC/PDIE, atactic is the only option via EMC. Use RadonPy with `tacticity="isotactic"` if stereospecific chains are required.

### `submit_emc_cell_job`

```python
job = submit_emc_cell_job(
    smiles="...",
    polymer_class="PCBN",   # determines force field automatically
    dp=20,                  # repeat units per chain
    density_initial=0.6,    # ~0.5× experimental density
    ntotal=3000,            # target total atom count; EMC sets nchains from this
    temperature=300.0,
    seed=-1,                # -1 = random seed
    output_name="polymer",
)
```

Poll with `get_emc_job_status(job_id)` until `status == "completed"`, then:

```python
out = get_emc_job_output(job_id)
data_path    = out["result"]["data_path"]     # absolute path to LAMMPS .data file
params_path  = out["result"]["params_path"]   # absolute path to emc_build.params (may be None)
lammps_flags = out["result"]["lammps_flags"]  # e.g. {"use_pcff": True, "use_opls": False}
# Pass both to generate_equilibration_workflow() in Stage 2
```

**Output placement:** After the job completes, copy both outputs into `{work_dir}/cell/`:

```bash
mkdir -p {work_dir}/cell
cp <data_path>   {work_dir}/cell/cell.data
cp <params_path> {work_dir}/cell/emc_build.params   # skip if params_path is None
```

Report `data_path = {work_dir}/cell/cell.data` and `emc_params_path = {work_dir}/cell/emc_build.params` in the RESULT block.

### density_initial Reference

| class_name | density_initial | Experimental RT density |
|---|---|---|
| PCBN (BPA-PC) | 0.60 | 1.20 g/cm³ |
| PAMD (Nylon-6) | 0.57 | 1.14 g/cm³ |
| PKTN (PEEK) | 0.65 | 1.30 g/cm³ |
| PSFO (PSU) | 0.65 | 1.24 g/cm³ |
| PIMD (Kapton) | 0.70 | 1.42 g/cm³ |
| PHAL (PVDF) | 0.89 | 1.78 g/cm³ |
| PHAL (PTFE) | 1.05 | 2.17 g/cm³ |
| PHYC (PE/PP/PIB) | 0.48 | 0.91–0.97 g/cm³ |
| PDIE (PBD/PI) | 0.45 | 0.90–0.91 g/cm³ |
| PSTR (PS) | 0.53 | 1.05 g/cm³ |

Use ~0.5× experimental — low enough to avoid steric clashes; Stage 2 compresses to full density.

### Known Warnings

- **PDIE (class 6):** `"Diene polymer: verify cis/trans geometry in SMILES — cis vs trans isomers can differ by ~60K in Tg."` Encode cis/trans microstructure explicitly (e.g. `*C/C=C\C*` for cis-PBD).

### Decision IDs for run_log.md (EMC path)

| ID | Decision | Value |
|---|---|---|
| D-01 | Force field | auto-selected from polymer_class (see `lammps_flags` in output) |
| D-02 | Charge method | embedded in FF — no separate step |
| D-03 | Electrostatics | pppm (all except PHYC/PDIE which use lj/cut) |
| D-04 | System size | dp and ntotal passed to submit_emc_cell_job |

---

## Path B — RadonPy (PURA only)

PURA (polyurea, class 12) cannot use EMC — PCFF is missing `{n_2, hn}` increment parameters. Always use GAFF2_mod with RESP charges.

### Rule A: Force Field AFTER Polymerization

**The single most costly mistake in this workflow.**

```
# ❌ WRONG — force field is lost during polymerization
assign_forcefield(monomer, "GAFF2_mod") → polymerize(ff_output)

# ✅ CORRECT
polymerize(monomer) → assign_forcefield(poly_output, "GAFF2_mod")
```

RadonPy's async polymerization job does not preserve FF parameters assigned to the monomer. Violation causes LAMMPS to fail with "unknown atom type."

### Workflow

```
build_molecule_from_smiles(smiles)
  └─ [optional] submit_conformer_search_job()
       └─ submit_assign_charges_job()        # RESP for PURA
            └─ submit_polymerize_job()        # ← NO ff assignment before this
                 └─ assign_forcefield("GAFF2_mod")
                      └─ submit_generate_cell_job()
                           └─ save_lammps_data()  → cell.data
```

### Tool Notes

**`build_molecule_from_smiles`** — SMILES must use `*` atoms as chain-end attachment points (e.g. `*NCC(=O)N*`).

**`submit_conformer_search_job`** — use `psi4_omp` parameter (not `omp`). Skip for simple linear monomers; use for branched or aromatic systems.

**`submit_assign_charges_job`** — use `charge_method="RESP"` for PURA (pppm electrostatics require high-quality charges). ESP is acceptable for fast screening.

**`submit_polymerize_job`** — DP guidelines: 50 = fast screening, 100 = standard production, 150 = publication quality. **Warning:** the tool overwrites `mol_file` in place — the input monomer JSON is gone after completion. Save a checkpoint first.

**`assign_forcefield`** — pass the polymer output, NOT the monomer. Synchronous.

**`submit_generate_cell_job`** — always use `density=0.05` to prevent overlap during packing; Stage 2 compresses to full density. Chain count: 6 ≈ 12 k atoms (fast), 10 ≈ 20 k (standard), 20 ≈ 40 k (publication).

**`save_lammps_data`** — synchronous. Save to `{work_dir}/cell/cell.data` (create the directory first: `mkdir -p {work_dir}/cell`). Pass this path to Stage 2.

### Checkpoint Saves

Save at each key stage to resume without re-running expensive QM steps:

```python
save_molecule(charged_monomer, "./checkpoints/01_charged_monomer.json", format="json")
save_molecule(polymer_output,  "./checkpoints/02_polymer.json",         format="json")
save_molecule(ff_output,       "./checkpoints/03_polymer_ff.json",      format="json")
save_molecule(cell_output,     "./checkpoints/04_cell.json",            format="json")
```

---

## Common Failures

**`classify_polymer` returns `class_id == 0`:** SMILES is malformed or missing `*` polymerization attachment points. Check that your SMILES uses `*CC*` or `[*]CC[*]` notation.

**"Unknown atom type" in LAMMPS later:** Force field was assigned before polymerization (RadonPy path). Re-run from the polymerize step.

**Conformer search crashes:** Check `psi4_omp` parameter (not `omp`).

**Cell generation fails with overlap:** Density too high for initial packing (RadonPy path). Always use `density=0.05`.

**Polymerization job hangs in "pending":** Check `list_all_jobs()` for stuck jobs. Cancel if needed.

**`submit_polymerize_job` overwrites `mol_file` in place:** Save checkpoints to distinct paths before running (see Checkpoint Saves).

**EMC exits with "Missing force field parameters":** Check SMILES conventions for the class — most common cause is `*` placement error (PCBN: `*` on aromatic C; PIMD: ring atoms must be lowercase). Verify the SMILES has exactly two `*` atoms. If `dp=20` fails, retry with `dp=15` — occasionally shorter chains avoid missing-increment errors.

---

**→ When `cell.data` is saved, return the RESULT block. The orchestrator decides next steps.**
