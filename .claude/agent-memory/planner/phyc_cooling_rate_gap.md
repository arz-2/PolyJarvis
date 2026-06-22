---
name: phyc-cooling-rate-gap
description: The melt->300 K cooling RATE is not expressible via decided_params or generate_equilibration_workflow; only partially slowable via add_melt_npt
ingested_at: 2026-06-20
metadata:
  type: project
---

A "lower cooling rate" / "Nx slower cool" request (e.g. PE density over-densification fix, revision.md Priority 0 R1 Major #4) is NOT fully expressible through the plan.

**Why:** In `generate_equilibration_workflow` (mcp-lammps-engine/server.py), the `npt_cool` ramp uses `N_STEPS=steps_npt`, which is **atom-count-tiered** (server.py ~L1154-1170), NOT driven by `t_equil_ns`. There is no `cool_steps`/`npt_cool_steps` argument. In `gen_prompt.py`, `t_equil_ns` is **display-only** (L280) — it is never threaded into the cool ramp. So no decided_param doubles the cool-ramp duration.

**How to apply:** When a corrected protocol asks for a slower cool:
- The threaded, real levers are: `npt_prod_ns`->npt_prod_steps, `melt_npt_ns`->melt_npt_steps (only with `add_melt_npt=true`), `T_equil_K`->melt-stage temp, `annealing_T_high_K`->max_temp.
- `add_melt_npt=true` gives a PARTIAL slowdown on the glass-formation descent because the final `npt_cool` shortens from max_temp->300 to T_equil_K->300 over the same steps_npt (e.g. 620->300 K vs 550->300 K ~ 1.28x). Quantify this, don't claim the full Nx.
- **CRITICAL: `add_melt_npt` is NOT plan-threaded.** gen_prompt.py reads it from argv (`getattr(args,'add_melt_npt')`, L253), NOT via `_pick` from cls/plan. `apply_plan` does not backfill it. So `decided_params.add_melt_npt=true` is a DEAD key unless the orchestrator ALSO passes the `--add_melt_npt` CLI flag on the equil-stage gen_prompt call. The documented CLAUDE.md equil call does NOT include it — so add an explicit `orchestrator_note` on the equil stage instructing the flag. `melt_npt_ns` IS picked from the plan once the branch fires. Lesson: jq confirms a key is IN the file, not that gen_prompt READS it — trace each override key to its `_pick`/`args` source.
- Encode-and-flag: set the residual as the dominant uncertainty (`kinetic_over_densification_cooling_rate`, reduction_probe `fast_density_screen`); do NOT edit server.py (planner scope creep, risks test_plan_reproducibility.py). Defer the full fix (cool-ramp step override or manual cool stage) to critic/orchestrator.
- Add a density-target detection gate to equil-check success_criteria: `overall_pass=True` is a convergence gate, NOT accuracy — a run can converge to a wrong (over-dense) plateau and pass. Pair it with a density band vs experimental (PE exp=0.95 g/cm3). See [[reasoned-override-keeps-confidence-high]].
