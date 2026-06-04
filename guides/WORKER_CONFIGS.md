# PolyJarvis Worker Configurations
**Version:** 1.0 | **Last updated:** 2026-06-03

Reference for orchestrators: model/color/memory settings, prompt templates, and RESULT block schemas for all four stage workers.

---

## Worker Summary

| Worker | Model | Color | Memory | Effort | Role |
|--------|-------|-------|--------|--------|------|
| `molecule-builder` | opus | 🔵 blue | project | high | SMILES → .data file |
| `equilibration-worker` | sonnet | 🟠 orange | project | inherit | .data → submitted chain |
| `tg-sweep-worker` | haiku | 🟣 purple | project | inherit | equil .data → submitted sweep |
| `analysis-worker` | opus | 🟢 green | project | high | logs → RESULTS block |

Model is set in the worker's `.claude/agents/*.md` frontmatter — **do not pass `model=` in Agent() calls** unless overriding the default for a specific run. Override example: `Agent(subagent_type="tg-sweep-worker", model="sonnet", ...)` if haiku fails.

Memory scope: `project` → `.claude/agent-memory/<worker-name>/` — committed to git, shared with collaborators.

---

## 🔵 molecule-builder

### Prompt template

```
smiles:            <SMILES string with exactly two * chain-end atoms>
run_name:          <RUN_NAME>                   # e.g. PS4, PMMA2
work_dir:          /home/arz2/simulations/<RUN_NAME>
polymer_class:     <class_name>                 # from classify_polymer(), e.g. PSTR
preferred_builder: emc | radonpy
preferred_ff:      pcff | opls-aa | trappe-ua | gaff2_mod
dp:                <int>                        # degree of polymerization
nchain:            <int>                        # number of chains
density_initial:   <float>                      # g/cm³, from polymer_rules.json
charge_method:     resp | am1bcc | none
electrostatics:    long-range | short-range | none
cutoff_A:          <float>
dt_fs:             <float>
phal_patch:        true | false                 # true if polymer_class == PHAL
ff_confidence:     high | medium | low          # from classify_polymer()
```

### RESULT block (success)

```
RESULT:
  data_path: /absolute/path/to/cell.data
  lammps_flags: {"use_pcff": false, "use_opls": false}
  polymer_class: PSTR
  ff: GAFF2_mod
  charge_method: AM1-BCC
  electrostatics: pppm
```

### RESULT block (failure)

```
RESULT:
  error: <concise description>
  last_step: <which step failed>
  action_needed: <what orchestrator should change or retry>
```

---

## 🟠 equilibration-worker

### Prompt template

```
data_path:         <absolute path to .data file from Stage 1>
lammps_flags:      {"use_pcff": true, "use_opls": false}
run_name:          <RUN_NAME>
work_dir:          /home/arz2/simulations/<RUN_NAME>
polymer_class:     <class_name>
T_equil_K:         <float>                      # from polymer_rules.json
P_equil_atm:       1.0
t_equil_ns:        <float>
T_anneal_high_K:   <float>
anneal_cycles:     <int>
gpu_ids:           "0,1,2,3"                    # verify with nvidia-smi first
mpi_ranks:         4
```

### RESULT block (success)

```
RESULT:
  chain_id: <chain_id from run_lammps_chain>
  stages_dir: /absolute/path/to/stages/
  expected_equil_data: /absolute/path/to/equil_final.data
  monitor_command: <monitor_command string from watch_run>
  gpu_ids_used: "0,1,2,3"
  n_atoms: <n_atoms from parse_data_file>
```

### RESULT block (failure)

```
RESULT:
  error: <concise description>
  step_failed: validate_data_file | generate_equilibration_workflow | run_lammps_chain
  action_needed: <what orchestrator should adjust>
```

---

## 🟣 tg-sweep-worker

### Prompt template

```
equil_data_path:   <absolute path to equilibrated .data file from Stage 2>
lammps_flags:      {"use_pcff": false, "use_opls": false}
polymer_class:     <class_name>
run_name:          <RUN_NAME>
work_dir:          /home/arz2/simulations/<RUN_NAME>/tg_sweep
tg_params:
  T_start:         <float K>                    # from polymer_rules.json tg_range + 150 K
  T_end:           <float K>                    # from polymer_rules.json tg_range - 100 K
  T_step:          <float K>                    # typically 10 K
  n_steps_per_t:   <int>                        # typically 500000–4000000
dt_fs:             <float>
gpu_ids:           "0,1,2,3"
mpi_ranks:         4
```

### RESULT block (success)

```
RESULT:
  run_id: <run_id from run_lammps_script>
  tg_log_path: /absolute/path/to/tg_sweep.log
  monitor_command: <monitor_command string from watch_run>
  gpu_ids_used: "0,1,2,3"
  T_start: <K>
  T_end: <K>
  T_step: <K>
  n_steps_per_t: <N>
```

### RESULT block (failure)

```
RESULT:
  error: <concise description>
  step_failed: generate_script | run_lammps_script
  action_needed: <what orchestrator should adjust>
```

**Note:** If tg-sweep-worker (haiku) fails to generate a valid RESULT block or skips steps, re-spawn with `model="sonnet"` override.

---

## 🟢 analysis-worker

### Prompt template

```
equil_log_path:    <absolute path to NVT production log (stage 06_nvt_production)>
npt_prod_log_path: <absolute path to NPT production log (stage 07_npt_production)>
tg_log_path:       <absolute path to Tg sweep log>
equil_data_path:   <absolute path to equilibrated .data file>
dump_path:         <absolute path to trajectory dump | null>
run_name:          <RUN_NAME>
polymer_class:     <class_name>
backbone_types:    [<int>, ...]                 # atom type IDs for backbone
tasks:
  - check_equilibration_comprehensive           # always
  - extract_tg                                  # always
  - extract_density                             # always
  - extract_bulk_modulus                        # always
  # add if requested:
  # - calculate_rdf
  # - extract_end_to_end_vectors
```

### RESULT block

```
RESULT:
  run_name: <RUN_NAME>
  equilibrated: true | false
  Tg_K: <value or N/A>
  Tg_fit_quality: EXCELLENT | GOOD | ACCEPTABLE | POOR | N/A
  Tg_r_squared: <value or N/A>
  Tg_exp_K: <experimental value from polymer_rules.json>
  Tg_status: OK (±<delta>K) | WARNING | N/A
  density_gcm3: <value or N/A>
  density_SEM: <value or N/A>
  density_exp_gcm3: <experimental value>
  density_status: OK (±<pct>%) | WARNING | N/A
  bulk_modulus_GPa: <value or N/A>
  bulk_modulus_uncertainty: <value or N/A>
  bulk_modulus_status: OK | WARNING | N/A
  equilibration_overall_pass: true | false
  equilibration_warnings: <list or N/A>
  optional_analyses: <summary of rdf/end-to-end results or N/A>
  overall_verdict: PASS | WARNING | FAIL
  notes: <flags, caveats, recovery suggestions>
```

---

## Model override reference

The frontmatter `model` field is the default. Override per-invocation only when needed:

```python
# Normal invocation — uses frontmatter model
Agent(subagent_type="tg-sweep-worker", description="🟣 Tg sweep PS", prompt=...)

# Override — escalate haiku to sonnet after a failure
Agent(subagent_type="tg-sweep-worker", model="sonnet", description="🟣 Tg sweep PS (retry)", prompt=...)
```

Model resolution order (from docs): env var → per-invocation → frontmatter → main session model.
