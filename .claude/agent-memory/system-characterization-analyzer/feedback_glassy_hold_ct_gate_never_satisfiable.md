---
name: feedback-glassy-hold-ct-gate-never-satisfiable
description: probe_tau_relax_reliable is structurally unattainable for glassy-class characterization runs, since the mandated npt_prod300 hold is below Tg by design
metadata:
  type: feedback
---

The procedure mandates the `npt_prod300` (300 K, below Tg) stationary hold for glassy classes as
the source of `chain.ct.tau_relax_ps`/`decay_fraction_at_end`. But a glassy hold's whole point is
that chains are kinetically trapped (`msd.kinetic_trap_flag=true` is *expected*, not a red flag) —
chains that haven't displaced their own size cannot decay C(t) meaningfully, so
`decay_fraction_at_end` will be ~0 and the KWW fit rails at its bound. The 0.15 reliability floor
will therefore fail for essentially every glassy SMILES's characterization run, meaning no
tau_relax-derived knob (`t_equil_ns`, `eq_annealing_cycles`, `ct_min_decay_melt`,
`K_deform_rate_inv_s`/`_slow`) can ever be derived for a glassy class via this procedure, and
`write_characterization_cache.py`'s "≥1 derived_* field" gate will always exit 1 for them.

Evidence from PLA1 (PEST, glassy): the melt-stage NVT hold (recorded earlier in this run's own
`run_log.md` D-05 block, 951 frames) gave τ_relax=102645 ps / 5% decayed / α=0.33 (not trapped) —
a real, non-degenerate C(t). The mandated `npt_prod300` glassy hold on the *same chain* gave a
railed τ_relax=2.275e9 ps / 0.1% decayed / α=0.042 (kinetic trap flagged true). Same polymer, same
run — the state point alone flips the gate from plausibly-passable to structurally-failing.

**Why:** the C(t) reliability floor (0.15) was presumably calibrated against melt-state C(t), where
real decay is physically expected within an accessible trajectory length. It was not re-examined
for the glassy hold this agent is required to use.

**How to apply:** do not treat a glassy SMILES's `probe_tau_relax_reliable=false` as a probe
failure or something to fix by re-probing a different stage — the procedure is explicit that the
melt stage is not the hold to use. This is expected, structural behavior for glassy classes, not a
per-run anomaly. If a future task ever asks this agent to re-derive tau_relax-gated knobs for a
glassy SMILES, expect it to be unattainable via this exact procedure without a protocol change
(e.g. sourcing C(t) from the melt-stage hold instead of npt_prod300) that is out of this agent's
scope to make. Worth flagging upstream if a maintainer asks why the cache has zero derived-K glassy
entries.
