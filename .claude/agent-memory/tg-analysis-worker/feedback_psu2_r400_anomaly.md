---
name: psu2_r400_recovery_failed
description: PSU2 r400 recovery sweep gives Tg=374.7 K, far below exp (463 K) and prior rates (r40/r160~500 K); indicates systematic cooling protocol error
metadata:
  type: feedback
---

## Symptom
- PSU2 r400 (recovery attempt 1) yields Tg_K=374.7 K with fit_quality=GOOD (R²=0.984)
- Prior rates (r40=498.4 K, r160=502.1 K) both ~500 K
- Experimental Tg ≈ 463 K (literature)
- Rate-independent Tg law: higher cooling rates → higher observed Tg; r400 should be ≥ r160 (502 K), not ≤ 375 K

## Root Cause
- Density curve shows smooth monotonic drop (1.198→1.06 g/cm³) with no obvious kink or change-in-slope at 374 K
- Bilinear fit partitions continuous curve into two spurious "branches" separated by noise, not a physical transition
- Suggests sweep **never equilibrated into glassy state** or **cooling protocol is broken** (e.g., wrong thermostat settings, velocities not rescaled, data file corrupted)
- Recovery attempt 1 failed; per policy, max 2 attempts/worker

## Fix/Workaround
- **Do not use r400 Tg in multirate analysis**—contaminated point invalidates log-linear fit
- If both recovery attempts fail (r400 < 450 K again), write UNRESOLVED to run_log and halt PSU2 run
- For future PSU runs: verify cooling script generates staircase temp changes (check tg_progress.jsonl), validate starting .data matches intended equilibration state, inspect raw density curve visually before extracting Tg

## Impact
- PSU2 multirate registry (r40, r160, r400) now suspect; r400 point must be discarded
- If slope_gate would fail anyway (negative b), single-rate fallback to r160 (highest 2 points)
- Suggests a cross-track issue with tg-sweep-worker script generation or data threading
