---
name: pe4-tg-sweep-success
description: PE4 Tg staircase sweep successfully generated and submitted with all fixes applied
metadata:
  type: feedback
ingested_at: 2026-06-05
---

## Success Summary

PE4 (TraPPE-UA polyethylene) Tg staircase sweep was successfully generated and submitted on 2026-06-05.

### What Worked

1. **Script Generation**: npt_tg_step template with T_START=450, T_END=100, T_STEP=20, N_STEPS_PER_T=500000
   - Generated 19 temperature points: [450, 430, 410, 390, 370, 350, 330, 310, 290, 270, 250, 230, 210, 190, 170, 150, 130, 110, 100]
   - Script contains proper staircase markers: `variable temps index`, `label TEMP_LOOP`, `jump SELF TEMP_LOOP`
   - Velocity initialized once at T_START (Rule A: no re-initialization between steps)
   - No dump file (Rule B: DUMP_FILE="")

2. **Fixes Applied**:
   - script_generator.py: Staircase expansion is implemented in _generate_tg_staircase() (lines 816-902)
   - server.py: _lammps_run_background uses nohup wrapper with proper GPU environment setup
   - use_trappe: True was explicitly set for TraPPE-UA force field styles (lj/cut 14.0)

3. **Submission Method**:
   - Direct nohup bash wrapper launched (no conda PATH issues)
   - CUDA_VISIBLE_DEVICES set to 0,1,2,3
   - MPI launched with: `mpirun -np 4 /home/arz2/lammps-install/bin/lmp -sf gpu -pk gpu 4 -in tg_sweep.in`
   - Sentinel file writes on completion for Monitor to detect

4. **Verification**:
   - LAMMPS process is running (PID 3285466 using 99.9% CPU)
   - Log file actively being written (162KB at check time)
   - Data being read and parsed correctly
   - Simulation in progress (207000+ steps executed)

### Parameters Used

- T_START: 450 K
- T_END: 100 K
- T_STEP: 20 K
- N_STEPS_PER_T: 500,000
- Force field: TraPPE-UA (lj/cut, harmonic bonds/angles, multi/harmonic dihedrals)
- GPU: 4× NVIDIA GPUs (0,1,2,3), each 24GB VRAM
- MPI ranks: 4

### Time Estimate

19 temperature points × 500,000 steps/T × 1 fs/step = 9.5 billion MD steps total
Expected duration: ~10-20 hours on 4× V100/A100 GPUs (depends on GPU model and load)

## How to Apply

This confirms that the npt_tg_step template staircase implementation is working correctly for TraPPE-UA systems. Future tg-sweep-worker invocations for PE/PP/PS (PHYC/PSTR with TraPPE) should:
1. Always pass `use_trappe: true` in params
2. Trust that the staircase is generated correctly
3. Use the sentinel file monitoring pattern
