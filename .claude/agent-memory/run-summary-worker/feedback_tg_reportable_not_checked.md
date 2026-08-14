---
name: feedback-tg-reportable-not-checked
description: generate_run_summary grades Tg as PASS/FAIL even when tg_summary.json marks it non-reportable (TG_REVIEW/tg_reportable=false) — orchestrator must override the resulting status in run_log.md, not report run_summary.json's Tg status verbatim.
metadata:
  type: feedback
---

`generate_run_summary` has no awareness of `tg_reportable`/`tg_gate_verdict` in `tg_summary.json` —
it reads `Tg_K` and grades it against the exp band regardless. On PMMA1 (2026-08-12), `tg_gate_verdict:
"TG_REVIEW"` / `tg_reportable: false` (method_gap 32.3K, human accepted non-reportable per
THERMAL_TRACK.md's halt-to-human step) still produced `results.tg.status: "FAIL"` with a computed
`error_pct` in `run_summary.json`, as if the fit were a normal reportable disagreement with
experiment.

**Why:** THERMAL_TRACK.md's TG_REVIEW/TG_NOT_REPORTABLE handling is orchestrator-side logic (see
`[Tg reportability]` block) — it was never threaded into `generate_run_summary` itself, so the tool
silently grades a fit whose transition point isn't localized as though it were a normal MD value.

**How to apply:** After `generate_run_summary`, always cross-check the source `tg_summary.json`'s
`tg_reportable`/`tg_gate_verdict` fields, not just `run_summary.json`'s `results.tg.status`. If
`tg_reportable=false`, the orchestrator's own run_log.md RESULTS table is authoritative — override
`run_summary.json`'s Tg status/error_pct there rather than reporting it verbatim (density/K sections
of `run_summary.json` are unaffected — this gap is Tg-specific). The `md_offset_K` /
`tg_offset_corrected_K` fields this note also flagged are gone: multirate Tg is legacy/opt-in, the
offset was annotation-only, and nothing ever passed `--tg_md_offset_K`, so it ran on its 100.0 K
default. Archived `run_summary.json` still carry the keys; new ones do not.
