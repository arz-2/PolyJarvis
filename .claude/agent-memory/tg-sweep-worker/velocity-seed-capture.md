---
name: velocity-seed-capture-kokkos-npt-tg-step
description: KOKKOS npt_tg_step template renders velocity seed at line N=1 per stage, must extract from deck after generation
metadata:
  type: feedback
---

**Rule:** Always extract and log the velocity seed (SEED_HOT) from the generated `tg_sweep.in` deck immediately after `generate_script()` returns, before submission. The seed is the 3rd whitespace-delimited token in the `velocity all create` line.

**Why:** Cross-track rule 2 requires capturing the seed for reproducibility, especially when `velocity_seed` input is null (random draw). The template auto-generates one at generation time; reading it back documents the exact seed that was used in the run for later replication.

**How to apply:** 
- After `generate_script(template_name="npt_tg_step", ...)` succeeds, immediately run:
  ```bash
  grep 'velocity all create' <work_dir>/tg_sweep/tg_sweep.in | awk '{print $5}'
  ```
  The 5th field (after "velocity", "all", "create", T_START) is the seed integer.
- Log this seed in the RESULT block as `velocity_seed: <integer>` (never null/-1, never omitted).
- Example: `velocity all create 440.0 859566 mom yes rot yes dist gaussian` → SEED_HOT=859566.
