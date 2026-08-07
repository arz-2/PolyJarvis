# Molecule Builder Guide
**Read when:** You have a SMILES string and need to produce a LAMMPS `.data` file.
**Worker:** molecule-builder — return RESULT block to orchestrator when done.

---

## Rules

**Rule 0:** Call `classify_polymer(smiles)` before anything else.
- `class_id == 0` (UNKNOWN): stop — SMILES is malformed or missing `*` attachment points.
- `warning` not None: log in run_log.md.
- `co_occurring_groups` non-empty: note in run_log.md.
- **Known false flag:** `classify_polymer` returns PHAL for PVC (`*CC(Cl)*`) — PVC is actually
  PVNL/PCFF (C–Cl is not PTFE-family). Build with the class specified in the approved plan; log
  the PHAL divergence in D-01.

**EMC path** (force field is auto-selected from `polymer_class` — never pass a `field` argument):
- `nchains` sets the **exact** chain count (EMC "number" mode) — pass the prompt's `nchain`.
  Leave `ntotal` unset (fallback only when `nchains<=0`).
- `emc_seed`: use the prompt's `emc_seed` when given (reproduces the exact cell); else draw a
  random integer. Never pass `seed=-1` — that means irreproducible.
- PPHS: PCFF has P=N backbone types but no polyphosphazene-specific validation — flag results.
- PURT: EMC aliphatic segments only; aromatic MDI fails.

**RadonPy path:**
- Force field must be assigned strictly **after** polymerization —
  `polymerize(monomer) → assign_forcefield(poly_output, "GAFF2_mod")`, never the reverse.
  RadonPy's async polymerize job does not preserve FF parameters assigned to the monomer;
  violating the order causes LAMMPS to fail with "unknown atom type".
- `submit_generate_cell_job` always uses `density=0.05` to prevent overlap during packing.

---

## Workflow

### Path A — EMC

```python
import random
emc_seed = emc_seed_from_prompt if emc_seed_from_prompt is not None else random.randint(1, 999999)
job = submit_emc_cell_job(
    smiles="...",
    polymer_class="PCBN",
    dp=20,
    nchains=10,          # from the prompt's `nchain`
    density_initial=0.6,
    temperature=300.0,
    seed=emc_seed,
    output_name="polymer",
)
```

Poll with `get_emc_job_status(job_id)` until `status == "completed"`, then:

```python
out = get_emc_job_output(job_id)
data_path    = out["result"]["data_path"]      # EMC writes emc_build.data (not polymer.data) — use verbatim
params_path  = out["result"]["params_path"]   # may be None
lammps_flags = out["result"]["lammps_flags"]  # e.g. {"use_pcff": True, "use_opls": False}
```

**Output placement:** After the job completes, copy outputs into `{work_dir}/cell/`:

```bash
mkdir -p {work_dir}/cell
cp <data_path>   {work_dir}/cell/cell.data
cp <params_path> {work_dir}/cell/emc_build.params   # skip if params_path is None
```

Report `data_path = {work_dir}/cell/cell.data` and `emc_params_path = {work_dir}/cell/emc_build.params` in the RESULT block.

### Path B — RadonPy

```
build_molecule_from_smiles(smiles)
  └─ [optional] submit_conformer_search_job()
       └─ submit_assign_charges_job()        # RESP for PURA
            └─ submit_polymerize_job()        # ← NO ff assignment before this
                 └─ assign_forcefield("GAFF2_mod")
                      └─ submit_generate_cell_job()
                           └─ save_lammps_data()  → cell.data
```

**Tool Notes:**
- `submit_conformer_search_job` — use `psi4_omp` parameter (not `omp`). Skip for simple linear
  monomers.
- `submit_assign_charges_job` — use `charge_method="RESP"`.
- `submit_polymerize_job` — overwrites `mol_file` in place — save a checkpoint first.
- `submit_generate_cell_job` — `density=0.05` (see Rules above).
- `save_lammps_data` — save to `{work_dir}/cell/cell.data` (create the directory first).

**Checkpoint Saves:**

```python
save_molecule(charged_monomer, "./checkpoints/01_charged_monomer.json", format="json")
save_molecule(polymer_output,  "./checkpoints/02_polymer.json",         format="json")
save_molecule(ff_output,       "./checkpoints/03_polymer_ff.json",      format="json")
save_molecule(cell_output,     "./checkpoints/04_cell.json",            format="json")
```

---

**→ When `cell.data` is saved, return the RESULT block** (see agent's Required output format).
Never set `emc_seed: -1` — the cell must be reproducible.
