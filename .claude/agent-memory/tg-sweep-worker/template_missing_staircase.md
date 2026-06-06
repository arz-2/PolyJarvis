---
name: npt-tg-step-missing-staircase
description: npt_tg_step template does not implement temperature staircase sweep — only generates single-T script
metadata:
  type: feedback
ingested_at: 2026-06-05
---

## Critical Issue

The npt_tg_step template and script_generator.py **do NOT implement** the temperature staircase sweep feature needed for Tg measurement.

### Evidence

1. Parameters T_START, T_END, T_STEP, N_STEPS_PER_T are accepted by `generate_script()` but never used
   - grep shows no usage of these params in script_generator.py lines
   - The parameters are stored in subs dict but npt_tg_step.in template has no {T_START}, {T_END}, {T_STEP} placeholders

2. Generated script for PE4 with T_START=450, T_END=100, T_STEP=20, N_STEPS_PER_T=500000:
   - Only 81 lines, contains single `run 100000` (not 500000 per T)
   - Hardcoded to T_TARGET=300.0K (midpoint), not a staircase
   - No LAMMPS variable loops (no `variable T_loop index`, no `label loop`, no `jump`)
   - Quits immediately after first temperature

### Root Cause

The npt_tg_step.in template is designed for a single temperature point (per docstring: "Chain for full T sweep").
The template has no mechanism to loop over T_START → T_END by T_STEP steps.

The script_generator would need to either:
1. Expand T_START/T_END/T_STEP into a LAMMPS variable loop within the template, OR
2. Generate multiple sequential runs with T_TARGET updated each time

Neither is implemented.

### How to fix

Modify npt_tg_step.in or script_generator.py to:
1. Accept T_START, T_END, T_STEP, N_STEPS_PER_T parameters
2. Build a LAMMPS loop structure like:
   ```lammps
   variable T_loop index <temps>  # e.g., 450 430 410 ... 100
   label tg_loop
   
   fix npt_tg all npt temp ${T_loop} ${T_loop} ${T_DAMP} iso ${P_TARGET} ${P_TARGET} ${P_DAMP}
   run ${N_STEPS_PER_T}
   unfix npt_tg
   write_data tg_step_${T_loop}_out.data  # or append to single file
   
   next T_loop
   jump tg_sweep.in tg_loop
   ```

### Current Workaround

None. The template cannot generate a proper Tg sweep script until this is fixed.

## When to apply

When tg-sweep-worker is asked to generate a Tg sweep:
1. Check if generated script contains only one `run` statement
2. Verify it has a LAMMPS temperature loop (variable T_loop, label, jump)
3. If not, return RESULT error: "npt_tg_step template missing staircase implementation"
4. Do NOT submit the script to Lambda Labs

This issue blocks STAGE_3 for PE4 and all other systems until fixed.
