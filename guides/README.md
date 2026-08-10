# guides/ — Agent Guides & Machine-Read Config

This directory holds **prompts and config for the agent pipeline**, not human tutorials
(human docs live in `docs/` and the root `README.md`). Four genres share the folder; the
key distinction is *who consumes each file*:

## 1. Worker guides — inlined into worker prompts by `orchestration/scripts/gen_prompt.py`

Never `Read` these directly during a run; `gen_prompt.py --stage <STAGE>` embeds the right
one into the worker's prompt.

| Guide | Stage / worker |
|---|---|
| `MOLECULE_BUILDER.md` | `build` → molecule-builder |
| `EQUILIBRATION.md` | `equil` → equilibration-worker |
| `EQUIL_CHECK.md` | `equil-check` → equilibration-checker |
| `THERMAL_SWEEP.md` | `tg` → tg-sweep-worker |
| `THERMAL_ANALYSIS.md` | `analyze-tg`, `analyze-tg-multirate` → tg-analysis-worker |
| `MURNAGHAN.md` | `murnaghan` → murnaghan-worker |
| `DEFORM.md` | `deform` → deform-worker |
| `BM_ANALYSIS.md` | `analyze-bm` → bulk-modulus-extractor |
| `REVISION_PARAMS.md` | Fixed seeds/params for replication runs (inlined into several stages; local-only, gitignored) |
| `EXP_LOOKUP.md` | exp-lookup background. **Currently not wired in** — the orchestrator composes the exp-lookup prompt inline (CLAUDE.md Phase C) |

## 2. Orchestrator-read guides — moved to `orchestration/`

The orchestrator phase/track guides (`FOUNDATION.md`, `THERMAL_TRACK.md`, `MECHANICAL_TRACK.md`,
`SUMMARY.md`, `DETERMINISTIC_REPLICATE.md`) live in
[`orchestration/tracks/`](../orchestration/README.md), and the planner/critic `decision_policy.json`
alongside the orchestration code in [`orchestration/`](../orchestration/README.md) — the
orchestrator `Read`s the phase docs on phase entry.

## 3. Machine-read config (JSON, not prose)

| File | Content | Consumers |
|---|---|---|
| `polymer_rules.json` | Per-class FF/Tg ranges, density targets, DP defaults, annealing cycles, engine defaults, exp bounds. The largest and most load-bearing file here. | `gen_prompt.py`, `make_deterministic_plan.py`, hardware scripts, orchestrator `jq` calls |

## 4. Ops / workflow docs (human- and orchestrator-read)

| Guide | Content |
|---|---|
| `RECOVERY_PLAYBOOK.md` | Failure-diagnosis playbook consulted by `/recover`. Generated + local-only (gitignored); regenerate via `python -m tools.runlog_miner --playbook -o guides/RECOVERY_PLAYBOOK.md` |

The engine/GPU/MPI policy docs (`HARDWARE.md`, `HARDWARE_STUDY.md`) live with the calibration
toolchain and cells in [`hardware/`](../hardware/); they are machine-specific notes, local-only
(gitignored) — rebuild them from `/calibrate-hardware` results on a new box.

## Backlog

Items with no compliant fix target yet (`.claude/agents/*.md` are static descriptors and are
never edited for worker-pattern findings; these three currently have nowhere else to live):

- **literature-grounding-worker has no dedicated `guides/STAGE_N_*.md`.** When one exists, add:
  WebFetch on a `doi.org/<doi>` link for Elsevier/ACS publishers often returns only a redirect
  notice (302), not content — if the source PDF is already available locally under `literature/`
  and has been `Read` with a matching title/DOI/journal header, treat that as sufficient
  verification rather than chasing the WebFetch redirect.
- **`critic.md`'s `system_characterization_cache.json` probe** (`jq --arg s "$CANONICAL_SMILES"
  '.[$s] // {...}'`) has no `jq -c 'type'` guard first — harmless today (the file is
  object-typed) but would hard-error on an array-typed file. `critic.md` isn't reachable via
  `gen_prompt.py`'s `STAGE_MAP`, so this needs a direct edit to that file by whoever next
  touches it, not a guide addition.
- **A robust "dangling uncertainty citation" check for `validate_run_plan.py`** (evidence prose
  claiming a risk is "recorded as uncertainty `X`" when `X` isn't actually in `uncertainties[]`)
  was scoped but not built: a blanket scan for snake_case-looking tokens in evidence text is too
  noisy against the real plan corpus (planners routinely coin descriptive pseudo-identifiers in
  prose — e.g. `t_range_brackets_experimental_tg`, `bilinear_fit_r_squared` — that were never
  meant as literal field references), and citations aren't consistently backtick-quoted either.
  A future pass needs a narrower signal (e.g. matching specifically on phrasing like "uncertainty
  (`name`)" or "recorded as ... uncertainty X") before this is safe to automate.
