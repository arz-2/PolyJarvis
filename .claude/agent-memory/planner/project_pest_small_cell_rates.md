---
name: project_pest_small_cell_rates
description: PCFF PEST cells <6000 atoms: only the r40 K/ns rate clears tg_min_steps_per_T=200k; avoid rates >100 K/ns
metadata:
  type: project
---

PEST class (PCFF/PPPM) with cells <6000 atoms: the tg_rate_note in polymer_rules.json warns that at T_STEP=20K and dt=1fs, only r40 K/ns yields >=200k steps per temperature. Rates of r160 (125k steps) and r400 (50k steps) fall below tg_min_steps_per_T=200k.

**Why:** PLA2 (dp=50, nchain=10) yields a moderate cell; the class note is embedded in polymer_rules.json under _tg_rate_note for awareness. The deterministic plan uses the class-default rates [40,160,400] K/ns — the slope-sign gate is the primary protection. This is informational for edge-case planning.

**How to apply:** If a PEST cell is small (<6000 atoms) and only density is adequate at r40, flag that r160/r400 may not satisfy tg_min_steps_per_T — treat those rates as advisory context for the Tg analysis worker. For standard dp=50/nchain=10 runs the deterministic defaults are correct.
