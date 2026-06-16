# PolyJarvis Worker Configurations
**Version:** 1.4 | **Last updated:** 2026-06-10

Reference for orchestrators: prompt templates for all stage workers. RESULT block schemas live in each worker's agent file.

---

## Inter-Stage Field Contract

Each worker's RESULT feeds the next worker's prompt. The table below is the authoritative schema chain — if a field is renamed in a RESULT block, update `gen_prompt.py` to match.

| Source worker RESULT field | → | Target worker prompt parameter |
|---|---|---|
| `molecule-builder.data_path` | → | `equilibration-worker` `data_path` |
| `molecule-builder.lammps_flags` | → | `equilibration-worker` `lammps_flags`; also `tg-sweep-worker`, `deform-worker` |
| `equilibration-worker.expected_equil_data` | → | `tg-sweep-worker` `equil_data_path` |
| `equilibration-worker.chain_id` | → | orchestrator `get_run_status` / `watch_run` |
| `tg-sweep-worker.tg_log_path` | → | `tg-analysis-worker` `tg_log_path` |
| `tg-analysis-worker.Tg_K` | → | orchestrator `is_glassy` decision only (not passed to any worker) |
| `tg-analysis-worker.Tg_fit_quality` | → | `property-analysis-worker` `d06_tg_fit_quality`; `gen_prompt.py --tg_fit_quality` |
| `equilibration-worker.npt_prod_log_path` | → | `property-analysis-worker` `npt_prod_log_path` |
| `born-worker.born_log_path` | → | `property-analysis-worker` `born_log_path` |
| `born-worker.born_matrix_file` | → | `property-analysis-worker` `born_matrix_file` |
| `born-worker.n_atoms` | → | `property-analysis-worker` `born_n_atoms` |

### RESULT validation

Before passing any RESULT to the next stage, validate required fields are non-null:

```bash
python3 scripts/validate_result.py --stage <STAGE> --result '<YAML block>'
```

Or inline in the orchestrator using `scripts/validate_result.py` as a library (see that file for `validate_result(stage, block)` function).

---

## 🔵 molecule-builder

### Prompt template

```
smiles:            <SMILES string with exactly two * chain-end atoms>
run_name:          <RUN_NAME>
work_dir:          /home/arz2/PolyJarvis/data/<RUN_NAME>/lammps
polymer_class:     <class_name>
preferred_builder: emc | radonpy
preferred_ff:      pcff | opls-aa | trappe-ua | gaff2_mod
dp:                <int>
nchain:            <int>
density_initial:   <float>
charge_method:     resp | am1bcc | none
electrostatics:    long-range | short-range | none
cutoff_A:          <float>
dt_fs:             <float>
phal_patch:        true | false
ff_confidence:     high | medium | low
```

---

## 🟠 equilibration-worker

### Prompt template

```
data_path:         <absolute path to .data file from Stage 1>
lammps_flags:      {"use_pcff": true, "use_opls": false}
run_name:          <RUN_NAME>
work_dir:          /home/arz2/PolyJarvis/data/<RUN_NAME>/lammps/equil
polymer_class:     <class_name>
T_equil_K:         <float>   # melt annealing temperature (above MD Tg); used for max_temp= and annealing
T_workflow_K:      <float>   # pre-computed by gen_prompt.py: 300.0 if exp_Tg<300 (rubbery), else T_equil_K → pass as temp= to generate_equilibration_workflow
P_equil_atm:       1.0
t_equil_ns:        <float>
T_anneal_high_K:   <float>  # → max_temp= in generate_equilibration_workflow (annealing ceiling)
anneal_cycles:     <int>
dt_fs:             <float>
t_npt_prod_ns:     <float ns | null>  # null = auto (steps_npt // 2 by atom-count tier)
npt_prod_steps:    <int | null>       # pre-computed: t_npt_prod_ns × 1e6 / dt_fs; pass as npt_prod_steps= to generate_equilibration_workflow
gpu_ids:           "0,1,2,3"
mpi_ranks:         4
```

---

## 🟣 tg-sweep-worker

### Prompt template

```
equil_data_path:   <absolute path to equilibrated .data file from Stage 2>
lammps_flags:      {"use_pcff": false, "use_opls": false}
polymer_class:     <class_name>
run_name:          <RUN_NAME>
work_dir:          /home/arz2/PolyJarvis/data/<RUN_NAME>/lammps/tg
tg_params:
  T_start:         <float K>
  T_end:           <float K>
  T_step:          <float K>
  n_steps_per_t:   <int>
dt_fs:             <float>
gpu_ids:           "0,1,2,3"
mpi_ranks:         4
```

**Note:** If tg-sweep-worker (haiku) fails to generate a valid RESULT block or skips steps, re-spawn with `model="sonnet"` override.

---

## 🔵 born-worker

**Stage 8 (glassy only).** Runs NVT Born matrix simulation (nvt_born template). Requires LAMMPS with EXTRA-COMPUTE.

### Prompt template

```
equil_data_path:   <absolute path to 09_npt_prod300_out.data (300 K, Phase 2)>
lammps_flags:      {"use_pcff": false, "use_opls": false}
polymer_class:     <class_name>
run_name:          <RUN_NAME>
work_dir:          /home/arz2/PolyJarvis/data/<RUN_NAME>/lammps/prop
is_glassy:         true | false
born_run_ns:       4.0
dt_fs:             <float>
gpu_ids:           "0,1,2,3"
mpi_ranks:         4
```

---

## 🔵 deform-worker

**Retained for optional cross-check.** No longer called in the default glassy path (replaced by born-worker). Can be invoked manually for rate-sensitivity diagnostics.

### Prompt template

```
equil_data_path:   <absolute path to 09_npt_prod300_out.data (300 K, Phase 2)>
lammps_flags:      {"use_pcff": false, "use_opls": false}
polymer_class:     <class_name>
run_name:          <RUN_NAME>
work_dir:          /home/arz2/PolyJarvis/data/<RUN_NAME>/lammps/prop
is_glassy:         true | false
K_deform_rate_inv_s: <float>
K_strain_max:      <float>
dt_fs:             <float>
gpu_ids:           "0,1,2,3"
mpi_ranks:         4
```

---

## 🟢 tg-analysis-worker

**Called once:** After Tg sweep completes (orchestrator step 13). Single-purpose — only runs `extract_tg`.

### Prompt template

```
tg_log_path:       <absolute path to Tg sweep log>
run_name:          <RUN_NAME>
polymer_class:     <class_name>
output_dir:        /home/arz2/PolyJarvis/data/<RUN_NAME>/raw/
graphs_dir:        /home/arz2/PolyJarvis/data/<RUN_NAME>/graphs/
tasks:
  - extract_tg
```

### RESULT schema (required fields for orchestrator validation)

`run_name`, `Tg_K`, `Tg_fit_quality`, `Tg_r_squared`, `Tg_exp_K`, `Tg_status`, `overall_verdict`, `output_dir`, `notes`

---

## 🟢 property-analysis-worker

**Called once:** After deform-worker (glassy) or equilibration (rubbery) completes (orchestrator step 16). Runs equilibration check, density, bulk modulus, and run summary.

**Note:** If tg-analysis-worker (haiku) fails to produce a valid RESULT block, re-spawn with `model="sonnet"` override.
**Note:** If property-analysis-worker (sonnet) fails, re-spawn with `model="opus"` override.

### Prompt template

```
equil_log_path:    <absolute path to 06_nvt_production log (melt, Phase 1)>
npt_prod_log_path: <absolute path to 09_npt_prod300 log (300 K, Phase 2)>
born_log_path:     <absolute path to nvt_born log | null>
born_matrix_file:  <absolute path to born_matrix.dat | null>
born_n_atoms:      <int from born-worker RESULT | null>
equil_data_path:   <absolute path to 09_npt_prod300_out.data (300 K, Phase 2)>
npt_prod_dump_path: <absolute path to 09_npt_prod300 dump (300 K, Phase 2) | null>
run_name:          <RUN_NAME>
polymer_class:     <class_name>
smiles:            <SMILES string>
ff:                <force field, e.g. pcff>
d06_tg_fit_quality: <Tg fit quality from tg-analysis-worker RESULT>
exp_tg_range:      [<min_K>, <max_K>]
exp_density_range: [<min_gcm3>, <max_gcm3>]
output_dir:        /home/arz2/PolyJarvis/data/<RUN_NAME>/raw/
graphs_dir:        /home/arz2/PolyJarvis/data/<RUN_NAME>/graphs/
is_glassy:         true | false
dt_fs:             <float>
backbone_types:    [<int>, ...]
tasks:
  - check_equilibration_comprehensive
  - extract_density
  - extract_bulk_modulus_born    # if is_glassy=True (Born+NVT method)
  - extract_bulk_modulus         # if is_glassy=False
  - generate_run_summary
  # - calculate_rdf              # optional
  # - extract_end_to_end_vectors # optional
```

### RESULT schema

**Required (orchestrator validation):** `run_name`, `equilibrated`, `density_gcm3`, `bulk_modulus_GPa`, `bulk_modulus_method`, `equilibration_overall_pass`, `overall_verdict`, `run_summary_path`, `output_dir`, `graphs_dir`

**Always present (full RESULT block):** `Tg_K`, `density_SEM`, `density_exp_gcm3`, `density_status`, `bulk_modulus_uncertainty`, `bulk_modulus_status`, `shear_modulus_GPa`, `youngs_modulus_GPa`, `equilibration_warnings`, `optional_analyses`, `notes`

