---
name: project-npt-pppm-is-decompress-ramp
description: npt_pppm (the stage used as the probe's "melt-hold") is actually a P_START(max_press)→P_FINAL(1atm) decompression ramp at max_temp, not an isothermal/isobaric hold
metadata:
  type: project
---

The 4th kept stage (`npt_pppm`) in the standard equilibration workflow ramps pressure from
`max_press` (e.g. 50000 atm) down to `press` (e.g. 1 atm) at constant `max_temp` — it is a
non-stationary decompression, not an isothermal hold. The system-probe-worker task procedure
calls this "the melt-hold `npt_pppm` stage that system-probe-analyzer measures relaxation off
of," but the underlying physics/thermostat state is changing throughout the whole window (not
just equilibrating around a fixed state point).

**Why:** matters for system-probe-analyzer's KWW fit — a decay curve measured across a
pressure ramp conflates structural relaxation with the volume/density response to the ramp
itself. Confirmed via server.py stage generation (npt_pppm P_START=max_press, P_FINAL=press,
T_START=T_FINAL=max_temp) for PVDF1 (data/PVDF1/lammps/probe/npt_pppm/npt_pppm.in).

**How to apply:** system-probe-worker should flag this explicitly in its RESULT (not silently
report npt_pppm as if it were a clean isothermal hold), so the analyzer/orchestrator can judge
whether the resulting KWW curve is trustworthy or whether a future protocol change (e.g. an
actual isothermal hold stage) is warranted. Do not attempt to improvise a fix by adding
`add_melt_npt=True` — that changes the stage sequence/count (9 stages, `npt_melt` inserted
later) and is out of scope for a 4-stage truncated probe. See also
[[feedback-melt-npt-steps-noop]].
