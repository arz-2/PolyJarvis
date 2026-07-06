---
name: error_query_script_and_db_missing
description: exp-lookup-worker is non-functional in this checkout — scripts/query_best_match.py and polymer_db.sqlite do not exist
metadata:
  type: feedback
---

On PSU3 the exp-lookup stage failed: the worker's only tool, `scripts/query_best_match.py`, does not exist in this checkout, and there is no `polymer_db.sqlite` anywhere (`find . -name 'polymer_db*'` → empty). So the condition-matched experimental DB lookup the Phase-C orchestrator step expects cannot run here.

Impact: orchestrator must fall back to `polymer_rules.json` experimental ranges (this is already the documented fallback when match_confidence=none — CLAUDE.md). For PSFO the gen_prompt run-summary defaults are correctly wide and matched experiment well: exp_tg_range [443,483] (PSU 463 K), exp_density_range [0.958,1.296] (PSU ~1.24), exp_K_range [4.0,5.5] (Zoller PVT). No manual tight floors needed — gen_prompt's fallback bands graded density+K correctly.

How to apply: either (a) ship `scripts/query_best_match.py` + `polymer_db.sqlite`, or (b) document that exp-lookup is optional and the orchestrator should skip it and rely on gen_prompt's polymer_rules-derived bands when the script/DB are absent (don't spawn exp-lookup-worker at all in that case — it just burns a turn returning an error). Repo-relative: stage writes nothing; downstream used `data/PSU3/raw/run_summary.json` exp bands from gen_prompt.
