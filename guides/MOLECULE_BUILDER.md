# Molecule Builder Guide
**Read when:** You have a SMILES string and need to produce a LAMMPS `.data` file.
**Worker:** molecule-builder — return RESULT block to orchestrator when done.

---

## Rule 0: classify_polymer is Always First

Call `classify_polymer(smiles)` before anything else.

- `class_id == 0` (UNKNOWN): stop — SMILES is malformed or missing `*` attachment points
- `warning` not None: log in run_log.md
- `co_occurring_groups` non-empty: note in run_log.md

---

## Path A — EMC

EMC builds the amorphous cell and assigns all FF parameters in one step — no conformer search, charge assignment, polymerization, or FF assignment needed. The force field is selected automatically from `polymer_class` — do not pass a `field` argument.

**Class notes:**
- PPHS: PCFF has P=N backbone types but no polyphosphazene-specific validation — flag results.
- PURT: EMC aliphatic segments only; aromatic MDI fails.

### `submit_emc_cell_job`

```python
import random
# Use the pinned seed from the prompt (`emc_seed:`) when given — that is how replication
# studies (guides/REVISION_PARAMS.md) reproduce the exact cell. Only draw a random seed
# when the prompt's emc_seed is null. NEVER use seed=-1 (EMC doesn't return the used seed).
emc_seed = emc_seed_from_prompt if emc_seed_from_prompt is not None else random.randint(1, 999999)
job = submit_emc_cell_job(
    smiles="...",
    polymer_class="PCBN",
    dp=20,
    nchains=10,          # exact chain count — pass the `nchain` value from the prompt
    density_initial=0.6,
    temperature=300.0,
    seed=emc_seed,       # always a specific integer so the run is reproducible
    output_name="polymer",
)
```

`nchains` sets the **exact** number of chains EMC builds (EMC "number" mode); always
pass the `nchain` value from your prompt. `ntotal` is only a fallback used when
`nchains<=0` — leave it unset.

Poll with `get_emc_job_status(job_id)` until `status == "completed"`, then:

```python
out = get_emc_job_output(job_id)
data_path    = out["result"]["data_path"]
params_path  = out["result"]["params_path"]   # may be None
lammps_flags = out["result"]["lammps_flags"]  # e.g. {"use_pcff": True, "use_opls": False}
# emc_seed is the value you generated above — include it in your RESULT block
```

**Output placement:** After the job completes, copy outputs into `{work_dir}/cell/`:

```bash
mkdir -p {work_dir}/cell
cp <data_path>   {work_dir}/cell/cell.data
cp <params_path> {work_dir}/cell/emc_build.params   # skip if params_path is None
```

Report `data_path = {work_dir}/cell/cell.data` and `emc_params_path = {work_dir}/cell/emc_build.params` in the RESULT block.

### Decision IDs for run_log.md

| ID | Decision | Value |
|---|---|---|
| D-01 | Force field | auto-selected from polymer_class (see `lammps_flags` in output) |
| D-02 | Charge method | embedded in FF — no separate step |
| D-03 | Electrostatics | pppm (all except PHYC/PDIE which use lj/cut) |
| D-04 | System size | dp and nchain passed to submit_emc_cell_job |

---

## Path B — RadonPy 


### Rule A: Force Field AFTER Polymerization

```
# ✅ CORRECT
polymerize(monomer) → assign_forcefield(poly_output, "GAFF2_mod")
```

Never assign FF before polymerization — RadonPy's async job does not preserve FF parameters assigned to the monomer. Violation causes LAMMPS to fail with "unknown atom type."

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

**`submit_conformer_search_job`** — use `psi4_omp` parameter (not `omp`). Skip for simple linear monomers.

**`submit_assign_charges_job`** — use `charge_method="RESP"`.

**`submit_polymerize_job`** — overwrites `mol_file` in place — save a checkpoint first.

**`submit_generate_cell_job`** — always use `density=0.05` to prevent overlap during packing.

**`save_lammps_data`** — save to `{work_dir}/cell/cell.data` (create the directory first).

### Checkpoint Saves

```python
save_molecule(charged_monomer, "./checkpoints/01_charged_monomer.json", format="json")
save_molecule(polymer_output,  "./checkpoints/02_polymer.json",         format="json")
save_molecule(ff_output,       "./checkpoints/03_polymer_ff.json",      format="json")
save_molecule(cell_output,     "./checkpoints/04_cell.json",            format="json")
```

### Decision IDs for run_log.md

| ID | Decision | Value |
|---|---|---|
| D-01 | Force field | from assign_forcefield call |
| D-02 | Charge method | from submit_assign_charges_job params |
| D-03 | Electrostatics | pppm |
| D-04 | System size | dp and nchain from prompt |

---

## Common Failures

**`classify_polymer` returns `class_id == 0`:** SMILES is malformed or missing `*` polymerization attachment points.

**"Unknown atom type" in LAMMPS later:** Force field was assigned before polymerization (RadonPy path). Re-run from the polymerize step.

**Conformer search crashes:** Check `psi4_omp` parameter (not `omp`).

**Cell generation fails with overlap:** Density too high (RadonPy path). Use `density=0.05`.

**Polymerization job hangs in "pending":** Check `list_all_jobs()`. Cancel if needed.

**EMC exits with "Missing force field parameters":** Check SMILES conventions for the class — most common cause is `*` placement error (PCBN: `*` on aromatic C; PIMD: ring atoms must be lowercase). Verify exactly two `*` atoms. If `dp=20` fails, retry with `dp=15`.

---

**→ When `cell.data` is saved, return the RESULT block.**
