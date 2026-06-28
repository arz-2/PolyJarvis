---
name: project_psfo_pcff_slope_gate_fragility
description: PSU (PSFO/PCFF) multirate Tg slope-gate FAILED on PSU3 — non-monotonic Tg vs rate over a 0.60-decade span; same PCFF aromatic fragility as PSTR/PVNL
metadata:
  type: project
---

PSU3 (PSFO/PCFF, bisphenol-A polysulfone, DP=25/8 chains, post-EXTEND cell). Three Tg sweeps [25,50,100] K/ns gave per-rate Tg = **502.0 / 534.6 / 496.8 K**, each an individually GOOD/EXCELLENT bilinear fit (R² 0.9929 / 0.9972 / 0.9965). But the values are **non-monotonic** (r50 is a high outlier; r25≈r100, slightly inverted), so the log-linear Tg-vs-ln(rate) fit has **slope −3.75 K, R²=0.016 → slope_gate_pass=FALSE**, tg_method=single_rate_fallback, tg_at_slow_rate_K=502.0. VF failed (<2 decades). Rates span only **0.60 decades** ([25,50,100]) — slope sign is noise-dominated, same failure mode as the PS PCFF and PVC PCFF slope-gate notes.

Decision (budget-constrained): the CLAUDE.md hard stop calls for re-running all 3 sweeps with a fresh seed (~23.5 h), but only ~13 h of the 48 h budget remained. **User chose to accept the slowest-rate Tg = 502 K with a slope-gate-failed / low-confidence caveat and finish the run** (density + bulk modulus). Staged registry rows were DISCARDED (not committed — contaminated, would bias cross-run multirate fits). is_glassy decided from exp Tg (463 K > 300) since the MD Tg must not route on a failed gate.

Final run grade: Tg 502 K vs exp 463 K = +8.4% (run-summary FAIL/flagged unreliable); density 1.184 g/cm³ ✓ (−4.5%); K 4.42 GPa ✓ (within 4.0–5.5). So PSFO/PCFF gives good density + K but an unreliable Tg whose slope-gate is seed/build-dependent — a fresh-seed reroll (PS3 precedent) is the prescribed fix when budget allows. Consider widening the PSFO rate span (≥1.2 decades, e.g. [10,40,160]) to make the slope better-determined. Repo-relative: `data/PSU3/raw/tg_r{25,50,100}/`, `data/PSU3/raw/tg_multirate_result.json`.
