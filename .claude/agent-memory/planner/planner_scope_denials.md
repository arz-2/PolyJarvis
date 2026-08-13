---
name: planner-scope-denials
description: Planner Bash/Read scope blocks jq on guides/*.json and Read on guides/MURNAGHAN.md — how to locate a class entry without burning ~12 bisecting Reads
metadata:
  type: feedback
---

The planner's tool scope denies **Bash on anything referencing `guides/*.json`** (so the `jq '.classes.<CLASS>' guides/polymer_rules.json` step written into planner.md fails outright) and denies **Read on `guides/MURNAGHAN.md`** ("outside your allowed context"). Read on `guides/polymer_rules.json` and `guides/system_characterization_cache.json` IS allowed.

**Why:** a per-agent context-boundary PreToolUse hook (commit 76df9fa) restricts each worker to its own guide + relevant rules JSON + `data/**` + agent-memory. The planner's own instructions still tell it to `jq` the rules file and, for some classes, to read MURNAGHAN.md — the docs and the hook disagree.

**How to apply:**
- Never plan on `jq`-ing the rules file. Use `Read` on `/home/arz2/PolyJarvis/guides/polymer_rules.json` instead.
- Locating a class entry cost ~12 blind 3-line bisecting Reads because classes are in no useful order. Faster route: run `make_deterministic_plan.py` FIRST — its `decided_params` already transcribes most class numbers — then Read a single ~110-line window around the class to pick up the fields the scaffold drops (`experimental_tg_K`, `experimental_density_gcm3`, `exp_K_GPa`, `bm_pressures_note`, `ff_note`, `notes[]`, `tacticity`, `ct_gate_reliable`). Class-entry start lines observed 2026-08-11 (drift with edits, re-bisect if off): PHYC ~435, PSTR ~535, PDIE ~876, POXI ~965, PSUL ~1058, PEST ~1133, PURA ~1350, PIMD ~1422, PSIL ~1740, PKTN ~1815, PSFO ~1895; `electrostatics_decision_guide` ~2100 marks the end of `classes`.
- The Bash denial is a *textual* path match, so shell tricks can slip past it — don't. Use `Read` on `polymer_rules.json` / `system_characterization_cache.json`; never work around the path matcher (confirmed 2026-08-11 on PEEK1).
- When a guide you were told to read is scope-denied, say so in the plan evidence and reason only from what you CAN read (e.g. the class's own `bm_pressures_note`) rather than paraphrasing the unreadable file. Do not route around the block by writing a script into `data/**` that opens the denied path.

**More denied paths confirmed 2026-08-11 (PMMA1 rung-3 re-plan):** `Read` on `orchestration/tracks/THERMAL_TRACK.md` is denied ("outside your allowed context"); `Bash` on `orchestration/scripts/gen_prompt.py` (even just `--help`) is denied too — only a specific allowlist of scripts (`validate_run_plan.py`, `canon_smiles.py`, `make_deterministic_plan.py`, `select_hardware.py`, `estimate_tg_group_contribution.py` confirmed working) is reachable, not the general `orchestration/scripts/` tree. Consequence: could not directly verify which `.data` file a downstream stage (e.g. `tg`) consumes — had to record the answer as a flagged `uncertainties[]` assumption (structural inference from `tg_t_high_K` vs `T_equil_K`) instead of a verified fact. If this recurs, note it in the plan rather than guessing or fabricating a verification.

Related: [[pdie-reasoned-plan]].
