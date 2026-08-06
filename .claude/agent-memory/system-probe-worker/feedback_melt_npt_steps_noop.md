---
name: feedback-melt-npt-steps-noop
description: melt_npt_steps arg to generate_equilibration_workflow does NOT shorten the npt_pppm stage — it only sizes the separate npt_melt stage gated by add_melt_npt=True
metadata:
  type: feedback
---

`generate_equilibration_workflow(melt_npt_steps=...)` is a no-op unless `add_melt_npt=True`
AND `t_equil_K` is set AND `temp < t_equil_K` (server.py ~line 1594-1600). In that branch it
sizes the extra `npt_melt` isothermal stage inserted between `npt_cool_melt` and `npt_cool`.
It never touches `npt_pppm`'s `N_STEPS`.

`npt_pppm`'s duration (`steps_comp`) is instead auto-derived purely from `n_atoms` (server.py
~line 1409-1427): <5000 atoms → 300000 steps, <15000 → 500000, else 1000000 — at whatever
`dt_prod` timestep the FF/engine combo selects (often 1.0 fs). There is no exposed parameter
to override this in the standard (`add_melt_npt=False`) 7-stage protocol.

**Why:** system-probe-worker's task procedure assumes `melt_npt_steps` truncates `npt_pppm`
into a short melt-hold for KWW-curve probing. It doesn't. Passed `melt_npt_steps=400000` for
PVDF1 (n_atoms=3620, target 400 ps) and the generated `npt_pppm.in` still had `N_STEPS=300000`
(300 ps) — the size-tier default for <5000 atoms, unaffected by the argument.

**How to apply:** Do NOT rely on `melt_npt_steps` to control probe duration. Compute the
size-tier default yourself from `n_atoms` before submitting and compare to the target
`probe_melt_ps`; if the default is already shorter than target (as it usually is, since these
tiers are tuned for cheap probing), that's fine — report the *actual* steps/duration used in
the RESULT (`npt_pppm_actual_steps`), not the computed-but-unapplied target. Do not hand-edit
the generated `.in` file to force the target — advisor guidance: not worth the loss of template
fidelity for ~100 ps of difference; let system-probe-analyzer/orchestrator decide if a longer
probe is needed on a rerun.

See also [[project-npt-pppm-is-decompress-ramp]].
