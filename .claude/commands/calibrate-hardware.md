---
description: Benchmark this machine's GPU/CPU and write optimal mpi/gpu defaults into hardware_policy
allowed-tools: Read, Bash, mcp__mcp-emc-server__submit_emc_cell_job, mcp__mcp-emc-server__get_emc_job_status, mcp__mcp-emc-server__get_emc_job_output
---

Calibrate PolyJarvis to the hardware this clone is running on. This measures throughput and
writes the per-FF `mpi`/`gpu` defaults into `guides/polymer_rules.json:hardware_policy` (what
`scripts/gen_prompt.py` consumes). Follow these steps exactly.

**Shared-box rule (non-negotiable):** never contend with other users. Stay polite — do NOT pass
`--allow-busy`. The tooling already gates on idle/process-free GPUs and measured CPU load, runs
`nice`d, and skips configs that would contend. If the box is busy, it records evidence but won't
overwrite the consumed defaults — that is the correct, safe outcome.

**1. Check current load before doing anything:**
```bash
python3 scripts/pick_gpu.py status
nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
```
Note which GPUs are idle and roughly how loaded the CPU is. If nothing is idle, tell the user
and stop (or agree to defer) — do not force it.

**2. Build two small throwaway benchmark cells** (skip any that already exist under `data/`):
one PCFF (class2 + PPPM) and one TraPPE-UA (lj/cut). Use `submit_emc_cell_job`, then poll
`get_emc_job_status` until `completed` and read `data_path` from `get_emc_job_output`:
- PCFF: `submit_emc_cell_job(smiles="*CC(*)(C)C(=O)OC", polymer_class="PACR", dp=20, nchains=10)`
- TraPPE-UA: `submit_emc_cell_job(smiles="*CC*", polymer_class="PHYC", dp=40, nchains=20)`
  (TraPPE-UA needs **bare `*`** chain caps — `[*]` brackets fail with a group-connect error.)
Each job writes `<output_dir>/emc_build.data` plus a sibling `*.params`.

**3. Dry-run the calibration** to preview the polite matrix and the planned policy change
(writes nothing):
```bash
nice -n 19 python3 scripts/calibrate_hardware.py \
    --cell <PCFF_data_path> --ff pcff \
    --cell <UA_data_path>   --ff trappe \
    --dry-run
```
Report to the user which configs will run vs. be skipped (and why).

**4. Apply** (drop `--dry-run`) once the dry-run looks sane:
```bash
nice -n 19 python3 scripts/calibrate_hardware.py \
    --cell <PCFF_data_path> --ff pcff \
    --cell <UA_data_path>   --ff trappe
```

**5. Verify and report:**
```bash
python3 -c "import json;hp=json.load(open('guides/polymer_rules.json'))['hardware_policy'];print('host',hp['host']);print('benchmarked',hp['values_are_benchmarked']);print('probe',hp['directional_probe'].get('calibration_note'))"
```
Summarize: detected host, the best config per FF (ns/day), whether `values_are_benchmarked`
flipped to `true` (clean sweep) or stayed `false` (partial/contended — note that a re-run on an
idle box is needed for the authoritative `by_forcefield` update). Confirm `pick_gpu.py status`
still reflects the box.
