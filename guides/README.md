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
| `EXP_LOOKUP.md` | exp-lookup background. **Currently not wired in** — the orchestrator composes the exp-lookup prompt inline (orchestration/ORCHESTRATOR.md Phase C) |

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

No compliant fix target yet (`.claude/agents/*.md` is off-limits for worker-pattern edits):

- **literature-grounding-worker has no dedicated guide.** WebFetch on `doi.org/<doi>` for
  Elsevier/ACS often 302-redirects without content — if a matching PDF was already `Read`
  locally under `literature/`, that's sufficient verification.
- **`critic.md`'s cache probe** has no `jq -c 'type'` guard before indexing
  `system_characterization_cache.json` — harmless today (object-typed), but `critic.md` isn't
  reachable via `gen_prompt.py`, so it needs a direct edit.
- **Dangling-uncertainty-citation check for `validate_run_plan.py`** (evidence claiming a risk
  is "recorded as uncertainty `X`" when `X` isn't in `uncertainties[]`) was scoped but not
  built — a snake_case token scan is too noisy (planners coin many pseudo-identifiers in prose
  that aren't real citations). Needs a narrower phrase-match signal first.
