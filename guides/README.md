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

## Backlog

Findings from ingested worker memory that need a decision, not a patch — recorded so they are
not rediscovered a third time.

- **Glassy characterization can never cache a τ-derived knob.** The procedure takes
  `chain.ct.tau_relax_ps` from the `npt_prod300` hold, which is below Tg by design, so
  `decay_fraction_at_end` ≈ 0 and the KWW fit rails — the 0.15 reliability floor (calibrated on
  melt-state C(t)) fails structurally and `write_characterization_cache.py`'s ≥1-derived-field
  gate always exits 1. PLA1 measured both on one chain: melt hold τ=102,645 ps / 5% decayed /
  α=0.33, `npt_prod300` τ=2.275e9 ps / 0.1% / α=0.042. Fixing it means sourcing glassy τ from
  the melt hold, which is a protocol change in the agent descriptor.
- **`PDIE.exp_K_GPa` pools two members** (cis-PBD 1.38, cis-PI 1.94) into one span, so a
  single-member run grades against a band no member has. `_exp_tg_range` already does run-name
  member resolution; `exp_K_GPa` would need the same per-member shape.
- **`PEST` carries no `experimental_density_gcm3`**, so every polyester run reports
  `no exp ref` for density. Needs a sourced amorphous value per member, not a class average.
- **Three workers have no editable guide.** literature-grounding-worker, planner, critic and
  system-characterization-analyzer carry their whole procedure in `.claude/agents/*.md`, which
  memory ingest may not edit, so their recurring findings (paywalls are the practical ceiling for
  numeric CTE values; WebSearch summaries misattribute numbers to the wrong paper; never
  reconstruct a DOI from recall; a rung-3 re-plan is not automatically an FF swap) have nowhere
  authoritative to land. Either give them `guides/` files like the simulation workers have, or
  accept that those lessons re-cost a run each time.

The engine/GPU/MPI policy docs (`HARDWARE.md`, `HARDWARE_STUDY.md`) live with the calibration
toolchain and cells in [`hardware/`](../hardware/); they are machine-specific notes, local-only
(gitignored) — rebuild them from `/calibrate-hardware` results on a new box.
