---
description: Host-match the per-FF engine defaults to this machine (revalidate shipped defaults + parity) and write hardware_policy
allowed-tools: Read, Bash, mcp__mcp-emc-server__submit_emc_cell_job, mcp__mcp-emc-server__get_emc_job_status, mcp__mcp-emc-server__get_emc_job_output
---

Host-match PolyJarvis to the hardware this clone runs on. The per-FF engine defaults
(`pcff`/`opls`→kokkos, `trappe`→gpu+neigh-yes, `gaff`→gpu) were benchmarked on one box and the
engine crossover is hardware-dependent — so on new hardware they are directional until re-measured
here. This **revalidates the shipped default per FF on this box**: runs the exact engine/mpi/gpu the
policy ships (no engine re-search), gates it with a run-0 parity vs CPU, and records host-matched
ns/day into `guides/polymer_rules.json:hardware_policy`. A clean host-matched pass flips
`values_are_benchmarked=true` (which silences the run-time `gen_prompt` nudge). Follow these steps.

**Shared-box rule (non-negotiable):** never contend with other users. Stay polite — do NOT pass
`--allow-busy`. The tooling gates on idle/process-free GPUs and measured CPU load, runs `nice`d, and
SKIPS configs that would contend. If the box is busy it records evidence but leaves
`values_are_benchmarked=false` — the correct, safe outcome; re-run on an idle window.

**1. Check current load before doing anything:**
```bash
python3 scripts/pick_gpu.py status
nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
cat /proc/loadavg
```
Note which GPUs are idle and how loaded the CPU is (loadavg ≫ core count ⇒ contended). If nothing is
idle or the CPU is saturated, tell the user and defer — do not force it.

**2. Cells come from the repo.** The four `hardware/CALIB_<FAM>/emc_build.{data,params}` cells are
committed, so no build is needed for the FFs that have one. If `hardware/CALIB_OPLS/` or `hardware/CALIB_GAFF/`
is still missing, build it ONCE on an idle window via `submit_emc_cell_job` (poll
`get_emc_job_status` → read `data_path` from `get_emc_job_output`), then copy
`emc_build.{data,params}` into `hardware/CALIB_<FAM>/` and commit:
- OPLS-AA: `submit_emc_cell_job(smiles="*CC(c1ccccc1)*", polymer_class="PHAL", dp=20, nchains=10)`
- GAFF2: `submit_emc_cell_job(smiles=<a GAFF class SMILES>, polymer_class="PURA", dp=20, nchains=10)`
The revalidator skips any FF whose cell is absent (and says so).

**3. Dry-run** to preview the polite plan per FF, the resolved shipped default, and KOKKOS
availability (writes nothing):
```bash
python3 hardware/calibrate_hardware.py --dry-run
```
Report which FFs will run vs. skip (and why). If the KOKKOS binary is absent, `pcff`/`opls` will be
shown falling back to `gpu/mpi4` — note that to the user.

**4. Apply** (drop `--dry-run`) once the dry-run looks sane and the box is idle:
```bash
nice -n 19 python3 hardware/calibrate_hardware.py
```
Each FF runs its shipped default (timed → ns/day) plus a run-0 parity vs CPU; a clean uncontended
pass with all parities PASS and no KOKKOS fallback sets `values_are_benchmarked=true`.

**5. Verify and report:**
```bash
python3 -c "import json;hp=json.load(open('guides/polymer_rules.json'))['hardware_policy'];print('host',hp['host']);print('benchmarked',hp['values_are_benchmarked']);print('note',hp['directional_probe'].get('calibration_note'))"
```
Summarize: detected host, per-FF `ns_per_day` + parity verdict, whether `values_are_benchmarked`
flipped to `true` (clean) or stayed `false` (and why — contended / parity / kokkos-absent). Confirm
`pick_gpu.py status` still reflects the box.

**Authoritative re-search (rare):** to re-derive the engine *winner* per FF (not just confirm the
shipped choice) — e.g. on very different hardware — use `--full` with explicit cells on a drained box:
`python3 hardware/calibrate_hardware.py --full --cell hardware/CALIB_PCFF/emc_build.data --ff pcff ...`.
