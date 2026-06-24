---
name: peg1_r40_recovery_template_fix
description: Use npt_tg_step for multi-T ramps; manually patch with /kk class2 styles for kokkos engine
metadata:
  type: feedback
---

**Rule:** Always use template `npt_tg_step` (not single-T variants) for Tg sweeps. The template generates the multi-temperature loop (`label TEMP_LOOP`, `variable temps index`) with velocity inherited across steps (no re-init).

**Why:** Earlier attempt used a single-T template and tried to wrap it in a manual temperature loop, causing synchronization issues and incorrect energy/pressure reporting.

**How to apply:** When generating with `engine="kokkos"`, the template will emit `pair_style lj/class2/coul/long` and class2 styles but WITHOUT /kk suffixes. Manual patch required:
- `pair_style lj/class2/coul/long` → `pair_style lj/class2/coul/long/kk`
- `kspace_style pppm` → `kspace_style pppm/kk`
- `bond_style class2` → `bond_style class2/kk`
- `angle_style class2` → `angle_style class2/kk`
- `dihedral_style class2` → `dihedral_style class2/kk`
- `improper_style class2` → `improper_style class2/kk`
- `neighbor 2.0 bin` → `neighbor 2.0 bin/kk`
- `package gpu 1` → `package kokkos gpu 1 comm no`

After patch: verify script has (a) `variable temps index 440 420 400 ... 100` (18 points), (b) class2/kk styles, (c) velocity init ONCE before loop (no re-init inside loop). Grep to confirm: `grep 'pair_style.*kk\|bond_style.*kk\|velocity all create' script.in`.
