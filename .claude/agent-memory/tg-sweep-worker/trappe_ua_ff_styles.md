---
name: trappe-ua-ff-styles-fix
description: TraPPE-UA Tg sweep scripts must explicitly set use_trappe=true to get correct force field styles
metadata:
  type: feedback
ingested_at: 2026-06-05
---

## Issue
When generating npt_tg_step scripts for TraPPE-UA systems (PE, PS, PP, etc.), the script generator was defaulting to GAFF2-style force fields (lj/charmm/coul/charmm, fourier dihedrals) instead of TraPPE-UA styles (lj/cut, multi/harmonic).

This happened because:
1. The generator checks `use_trappe` flag at line 825 of script_generator.py
2. If not explicitly set to True, it defaults to False
3. When use_pcff=False AND use_opls=False AND use_trappe=False, the generator assumes GAFF2

## Solution
**Always pass `use_trappe: true` in the params dict when calling generate_script() for TraPPE-UA systems.**

### Correct TraPPE-UA params
```python
params = {
    "T_START": 450,
    "T_END": 100,
    "T_STEP": 20,
    "N_STEPS_PER_T": 500000,
    "use_trappe": true,  # ← REQUIRED for TraPPE-UA
    "use_pcff": false,
    "use_opls": false,
    "use_pppm": false,   # TraPPE-UA has no electrostatics
    "use_shake": false,  # TraPPE-UA is united-atom, no explicit H
    "params_file": "/path/to/emc_build.params",
    # ... other params
}
```

### Resulting force field styles (correct)
```
pair_style lj/cut 14.0
bond_style harmonic
angle_style harmonic
dihedral_style multi/harmonic
improper_style none
special_bonds lj 0 0 0
pair_modify mix arithmetic tail yes
```

## How to apply
When orchestrator spawns tg-sweep-worker for PHYC (PE/PP/PIB):
1. Check lammps_flags in the prompt
2. If use_pcff=false and use_opls=false → polymer is TraPPE-UA
3. Always add `use_trappe: true` to the params dict passed to generate_script()

This fixes the failure from run b8053b95 (PE4).
