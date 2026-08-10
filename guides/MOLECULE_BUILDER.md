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
- Tacticity: `submit_emc_cell_job` has no tacticity/stereochemistry parameter. If the plan names
  a tacticity, report it as "not enforced/not verifiable" rather than asserting the requested
  value — only RadonPy's `submit_polymerize_job(tacticity=...)` actually honors it.

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

`get_emc_job_status` reports no progress fraction, so prefer blocking on the artifact over
repeated status polls (foreground `sleep N; ls` is blocked by the Bash tool):

```bash
until [ -f <output_dir>/emc_build.data ]; do sleep 5; done   # generous timeout
```

Then call `get_emc_job_output(job_id)` once:

```python
out = get_emc_job_output(job_id)
data_path    = out["result"]["data_path"]      # EMC writes emc_build.data (not polymer.data) — use verbatim
output_dir   = out["result"]["output_dir"]
params_path  = f"{output_dir}/emc_build.params"  # get_emc_job_output has no params_path key — EMC always writes this fixed basename into output_dir
lammps_flags = out["result"]["lammps_flags"]  # e.g. {"use_pcff": True, "use_opls": False}
```

**Output placement:** `work_dir` already ends in `/cell` (the orchestrator prompt appends it) —
copy outputs directly into `{work_dir}`, not `{work_dir}/cell/`:

```bash
mkdir -p {work_dir}
cp <data_path>   {work_dir}/cell.data
cp <params_path> {work_dir}/emc_build.params
```

Report `data_path = {work_dir}/cell.data` and `emc_params_path = {work_dir}/emc_build.params` in the RESULT block.

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
- `save_lammps_data` — save to `{work_dir}/cell.data` (`work_dir` already ends in `/cell`;
  create the directory first if needed).

**Checkpoint Saves:**

```python
save_molecule(charged_monomer, "./checkpoints/01_charged_monomer.json", format="json")
save_molecule(polymer_output,  "./checkpoints/02_polymer.json",         format="json")
save_molecule(ff_output,       "./checkpoints/03_polymer_ff.json",      format="json")
save_molecule(cell_output,     "./checkpoints/04_cell.json",            format="json")
```

---

## Known Failures

- **EMC binary expiry** — `submit_emc_cell_job` fails instantly (exit 255, ~0.15s) with
  `Error: main: Validity has run out; please download a fresh version.` This is
  class/SMILES-independent — do not misdiagnose as a SMILES/`*`-placement/FF problem, and do
  not retry with a smaller `dp`. Fix: swap only `~/emc/bin/emc_linux_x86_64` from a fresh
  SourceForge `montecarlo`-project tarball; never overwrite `~/emc/field/`, `~/emc/scripts/`,
  `~/emc/templates/` (the field tree carries local parameter patches). The sandbox denies both
  executing a freshly downloaded binary and writing to `~/emc/bin/` — diagnose and stage the fix
  (download/extract/diff are allowed) but emit the failure RESULT with the exact tarball URL and
  `cp` commands for the orchestrator/human to apply; do not reach for
  `dangerouslyDisableSandbox`.

---

**→ When `cell.data` is saved, return the RESULT block** (see agent's Required output format).
Never set `emc_seed: -1` — the cell must be reproducible.
