---
name: feedback-extend-mode-temp-matches-dwell-state
description: extend-mode npt_extend temp must match the checkpoint's actual state (melt T or 300 K), not default to 300 K
metadata:
  type: feedback
---

In `mode: extend`, the `npt_prod_temp_K` passed to `generate_equilibration_workflow(temp=...)` must
match the temperature of the checkpoint being extended, not automatically assume 300 K post-cool.

**Why:** PEEK1 (2026-08-11) extended `npt_production_out.data` from a phase=melt chain where
cooldown (`npt_cool300`/`npt_prod300`) had never run — the checkpoint was still at melt T (770 K).
The orchestrator's /recover MELT-MIXING rule states "match temp to the state you are actually
dwelling longer at." Passing 300 K would have quenched the melt cell instantly and destroyed the
checkpoint's physical validity (the extension is meant to converge density_drift at melt
conditions before cooldown ever runs).

**How to apply:** When a `mode: extend` prompt specifies `npt_prod_temp_K` explicitly and differs
from 300 K, trust it and pass it through unmodified to `temp=` — do not "correct" it to 300 K.
Verify the returned stage's `T_START`/`T_FINAL` in the workflow JSON match the requested temp
before submitting, since a silent default-temp bug here would be a difficult, expensive-to-detect
failure (full quench of a melt-phase cell).
