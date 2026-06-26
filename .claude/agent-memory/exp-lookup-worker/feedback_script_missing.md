---
name: query-best-match-script-missing
description: db/query_best_match.py does not exist — orchestrator stage guide references nonexistent script
metadata:
  type: feedback
---

**Symptom:** Experimental lookup stage fails with FileNotFoundError when trying to run `python3 db/query_best_match.py` (repo-relative; resolved against `<repo_root>` at runtime).

**Root cause:** The `db/query_best_match.py` script referenced in the stage guide is not present in the repository. The `db/` directory does not exist either.

**Fix/Workaround:** Either (1) create the script with polymer_db.sqlite querying logic, or (2) modify the orchestrator stage guide to fall back to polymer_rules.json ranges when match_method is unavailable. The stage guide should not reference tooling that doesn't exist.

**Context:** Script is called as part of PHASE C (SUMMARY) after experimental lookup, before run-summary-worker. This is a hard blocker for any run using the exp-lookup-worker stage.
