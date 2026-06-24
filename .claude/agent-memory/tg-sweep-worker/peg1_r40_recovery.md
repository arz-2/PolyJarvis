---
name: peg1_r40_recovery_template_fix
description: PEG1 Tg sweep rate-index 0 (40 K/ns) fixed by using correct npt_tg_step template with temperature ramp
metadata:
  type: feedback
---

**Rule:** For Tg temperature-ramp sweeps (multi-T cooling), always use `template_name="npt_tg_step"` with T_START, T_END, T_STEP parameters. Do NOT use single-temperature NPT templates.

**Why:** Prior attempts on this run (PEG1, rate_index 0, 40 K/ns) generated wrong script templates (e.g., single-T npt, or FF style errors). The npt_tg_step template correctly produces a temperature loop with `variable temps index [T1 T2 ... Tn]` and `jump SELF TEMP_LOOP`, holding n_steps_per_t at each point.

**How to apply:** When orchestrator passes T_start, T_end, T_step, n_steps_per_t parameters, always:
1. Call `generate_script(template_name="npt_tg_step", data_file=..., params={T_START, T_END, T_STEP, N_STEPS_PER_T, use_pcff/opls/trappe flags, DT, ...})`
2. Verify the output .in has: (a) multi-temp `variable temps index` line spanning T_start→T_end, and (b) correct FF styles (class2 for PCFF, etc.)
3. Never override with a single-T template even if earlier attempts failed.

**Related:** [[pcff_class2_styles]]
