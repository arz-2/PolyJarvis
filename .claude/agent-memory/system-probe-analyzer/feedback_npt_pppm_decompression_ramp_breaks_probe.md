---
name: feedback-npt-pppm-decompression-ramp-breaks-probe
description: npt_pppm probe stage is a non-stationary decompression ramp, structurally incapable of yielding reliable tau_relax or K0 — a probe-protocol gap, not a threshold problem
metadata:
  type: feedback
---

The `npt_pppm` stage used as the melt-hold probe (system-probe-worker's `probe_melt_log_path`/
`probe_melt_dump_path`) runs NPT at **constant T but with pressure ramped** from a high
compression value down to 1 atm over the entire window (observed: PVDF1, 50000→1 atm at 780 K
over 300 ps) — not a stationary (T,P) hold. Confirmed in `data/PVDF1/lammps/probe/npt_pppm/npt_pppm.in`
(`fix npt_fix all npt temp 780.0 780.0 100.0 iso 50000.0 1.0 1000.0`).

Both probe measurements this analyzer relies on assume stationarity:
- KWW `C(t)` fit for `tau_relax_ps` — a monotonically relaxing box under a pressure ramp does not
  sample equilibrium chain-relaxation dynamics.
- `K_T = kB*T*<V>/Var(V)` volume-fluctuation method — `Var(V)` under a ramp is dominated by the
  imposed drift, not equilibrium fluctuations.

**Result (PVDF1, PHAL, first invocation of this worker):** both reliability gates failed by more
than an order of magnitude simultaneously — `decay_fraction_at_end=0.007` vs the 0.15 floor (~21x
under), and K0 `sem/mean=24.18` vs the 0.15 ceiling (~160x over) — independently corroborated by
`volume_drift_pct=34.25%` (p≈1.8e-56) and `density_drift_pct=31.9%` (p=0.0) in the same tool
outputs. This was not a borderline call the 0.15 thresholds got wrong — both thresholds correctly
rejected badly-conditioned data. **The thresholds themselves are validated by this run, not the
thing to fix.**

**Why:** the probe worker's melt-hold stage was designed/reused from a compression-ramp protocol
(likely inherited from an existing equilibration-chain stage naming convention: `npt_pppm` sits
between `npt_compress` and presumably a subsequent stationary hold in the full equilibration
chain, but the probe apparently invokes just this ramp segment in isolation).

**How to apply:** when `analyze_probe` reports both `probe_tau_relax_reliable=false` AND
`probe_K0_reliable=false` together, check whether the probe log's `fix npt ... iso P1 P2 ...` has
`P1 != P2` (a ramp) before assuming it's simply "a bad probe" or "thresholds too tight" — if it's a
ramp, no threshold adjustment fixes it. The real fix belongs upstream in the system-probe-worker:
append a short stationary isothermal/isobaric hold (fixed P) after the decompression ramp so C(t)
and volume-fluctuation measurements sample equilibrium behavior. Flag this to the orchestrator/
system-probe-worker maintainers rather than loosening `probe_tau_relax_reliable`/`probe_K0_reliable`
thresholds in this agent.

See also [[project-cache-writes-zero-value-entries-on-probe-failure]].
