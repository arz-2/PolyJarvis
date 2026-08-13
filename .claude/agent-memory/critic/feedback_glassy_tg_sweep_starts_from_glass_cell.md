---
name: glassy-tg-sweep-starts-from-glass-cell
description: For glassy polymers the Tg sweep starts from npt_prod300_out.data (the 300 K glass), not the melt cell — verify this before accepting any "Tg is independent of the cooled-cell defect" claim
metadata:
  type: feedback
---

A plan claiming the Tg sweep restarts from the 550 K melt cell (`npt_production_out.data`) is
wrong for **glassy** systems. Chain of evidence, both checkable in seconds:
`orchestration/tracks/FOUNDATION.md:37` — `npt_tg_prep_data` is non-null only for RUBBERY
polymers, **null for glassy**; `orchestration/tracks/THERMAL_TRACK.md:23` — with no
`npt_tg_prep_data` the tg-sweep worker gets `--data_path $npt_prod300_out_data`. So the sweep
starts from the same 300 K cell whose density may carry an accepted deficit.

**Why:** PMMA1 (2026-08-11, rung-3 re-plan) accepted a -5.40% quench-rate-limited density and
argued in D-06 that Tg was clean because the sweep sourced the melt file. That was an inference
the planner explicitly flagged as unverified — and it is false. The conclusion may still survive
on different physics (T_START=600 K is ~222 K above exp Tg, so the frozen-in free volume should
be erased in the first liquid bins), but that is a different argument requiring its own check.

**How to apply:** when a plan accepts a deviant 300 K cell and asserts one property escapes the
deviation, do not accept a source-file argument on its face — re-derive it from
FOUNDATION.md/THERMAL_TRACK.md. If the sweep does start from the deviant glass, demand a concrete
zero-extra-GPU verification instead: compare the sweep's own high-T density bins (600/580/560/550 K)
against the melt anchor; matching ⇒ quench history erased; still low ⇒ Tg inherits the deviation
and must carry the same annotation. See [[plan-annotations-never-reach-worker-prompts]].
