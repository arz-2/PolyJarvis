# Born Matrix Guide
**Read when:** You are the born-worker and need to submit the NVT Born matrix simulation.
**Scope:** Script generation and job submission only. Property extraction from the Born output is handled by `bulk-modulus-extractor` (`extract_bulk_modulus_born`).

---

## Rules

### Rule A: Starting Structure is the NPT 300 K Production Output (`npt_prod300`)

The input `.data` file is `npt_prod300_out.data`.

> Do not use `npt_production_out.data` — that is the melt NPT run at `T_equil_K`, not the glassy 300 K output.

### Rule B: Glassy Polymers Only

If `is_glassy=False`, return immediately:

```
RESULT:
  run_id: null
  monitor_command: null
  born_log_path: null
  born_matrix_file: null
  n_atoms: null
  is_glassy: false
  n_stages: 0
```

### Rule C: Requires LAMMPS Compiled with EXTRA-COMPUTE

`compute born/matrix numdiff` is in the EXTRA-COMPUTE package. Verify the binary has this capability by checking:
```
/home/arz2/lammps/build/lmp_gpu -h 2>&1 | grep -i born
```
If the output is empty, the binary lacks EXTRA-COMPUTE — escalate to orchestrator.

### Rule D: NVT Ensemble — No Pressure Coupling

Do not use NPT for this run.

### Rule E: THERMO_FREQ Must Be ≤ 1000

Do not increase THERMO_FREQ beyond 1000.

### Rule F: All Scripts via generate_script — No Hand-Written .in Files

Use `nvt_born` template. Call `get_template_defaults("nvt_born")` for the full parameter list.

### Rule G: Run Length Cap — born_run_ns ≤ 0.5

The `compute born/matrix numdiff` trigger runs 6 full force evaluations every `BORN_EVERY=10` steps,
reducing effective throughput to ~8–20 steps/s even on a fast CPU. Affine Born terms converge in
~100–200 blocks (= 0.1–0.2 ns at BORN_EVERY=10, BORN_REPEAT=100, dt=1 fs). The gen_prompt.py
default is **0.5 ns**; do not exceed it without explicit orchestrator approval. (PEEK1 ran 4 ns →
projected 130 h; affine terms were converged at 87 blocks / ~0.09 ns.)

---

## Born Matrix Workflow

```python
# Inspect n_atoms from input file
info = inspect_data_file(data_file=equil_data_path)
n_atoms = info["n_atoms"]

params_born = {
    "LOG_FILE":          "nvt_born.log",
    "WRITE_DATA_FILE":   "nvt_born_out.data",
    "DUMP_FILE":         "nvt_born.dump",
    "LAST_DUMP_FILE":    "nvt_born_final.dump",
    "T_START":           300.0,
    "T_FINAL":           300.0,
    "T_DAMP":            100.0,            # 100 × dt_fs
    "TIMESTEP":          dt_fs,            # 1.0 fs default
    "N_STEPS":           n_steps,          # born_run_ns × 1e6 / dt_fs
    "THERMO_FREQ":       1000,
    "DUMP_FREQ":         10000,
    "BORN_NUMDIFF_DELTA": 0.0001,          # finite-diff displacement (Å)
    "BORN_EVERY":        10,               # samples taken every N steps
    "BORN_REPEAT":       100,              # samples per average block
    "BORN_FREQ":         1000,             # output frequency (= THERMO_FREQ)
    "BORN_MATRIX_FILE":  f"{work_dir}/mechanical/born/born_matrix.dat",
    "use_gpu":           False,    # CPU run: long NVT + restart safe
    **lammps_flags,
}
generate_script(
    template_name="nvt_born",
    data_file=equil_data_path,
    output_script=f"{work_dir}/mechanical/born/nvt_born.in",
    params=params_born,
)
run_id = run_lammps_script(
    script=f"{work_dir}/mechanical/born/nvt_born.in",
    work_dir=f"{work_dir}/mechanical/born",
    log_file="nvt_born_run.log",
    gpu_ids=gpu_ids,
    mpi=mpi_ranks,
)
w = watch_run(run_id)
# Return run_id and w["monitor_command"] to orchestrator. Do NOT call Monitor.
```

---

## Recovery Notes

**`compute born/matrix` syntax error:** Correct form is `compute born/matrix numdiff {DELTA} {VIRIAL_COMPUTE_ID}`. The virial compute (`born_press` in the template) must be defined *before* the born/matrix compute. Do not reorder.

**LAMMPS segfault or "unknown compute style born/matrix":** Binary lacks EXTRA-COMPUTE. Escalate to orchestrator — do not re-run with a different template.

**Born matrix file empty after run:** Verify BORN_FREQ == BORN_EVERY × BORN_REPEAT (default: 10 × 100 = 1000).

**Unphysical K (negative or far out of range):** Before suspecting column order or the formula, check `block_averaging.block_K_GPa_values` in `bulk_modulus_born.json`. Values growing in magnitude across blocks (e.g. `[-19,-18,-18,-29,-25]`) = non-stationary glass (failed upstream equil / under-density) inflating the `-(V/kT)Var(P)` fluctuation term — root cause is upstream, not the extractor. A converged glass gives stationary blocks. Recovery is the deform fallback, NOT re-running the born extractor with a different `eq_fraction`; report Born K as FAIL with the unphysical flag. (PMMA4: K_T=−21.9 GPa from CV=25.8% under-dense equil.)
