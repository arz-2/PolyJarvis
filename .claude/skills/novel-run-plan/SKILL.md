---
name: novel-run-plan
description: "Plan a PolyJarvis molecular-dynamics simulation for a polymer SMILES that hasn't been validated yet. Args: -run_name, -smiles (a repeat-unit SMILES with two `*` chain-end connection points), and -properties (properties to target)."
---

This skill takes three arguments, parsed from $ARGUMENTS:
- `run_name` — identifier for this run (used as `data/<run_name>/`)
- `smiles` — the repeat-unit SMILES string, with exactly two `*` chain-end connection points
- `properties` — comma-separated list of properties

State which of the three were parsed from $ARGUMENTS and which are missing, then ask the user to fill in whatever is missing before proceeding.

## 1. Determine novelty

- Canonicalize: `python3 orchestration/scripts/canon_smiles.py '<smiles>'` (radonpy env by default; `--env <env>` if renamed).
- Look up the canonical SMILES in `guides/system_characterization_cache.json`.
  - `protocol_validated: true` AND `validated_properties` covers every requested property → **not novel**: stop, use `python3 orchestration/scripts/make_deterministic_plan.py --run_name <name> --polymer_class <CLASS> --smiles '<smiles>' --properties <props>` instead.
  - Otherwise → `decision_policy.json`'s `confidence_gate.novel_or_partially_validated`: `plan_mode = reasoned`. Every decision below needs real reasoning and evidence, not a fast-path guess.

`make_deterministic_plan.py` performs this same canonicalize-and-lookup check itself once `--smiles` is passed (`make_plan_from_cache`), replaying the exact frozen protocol a prior completed campaign for this SMILES validated rather than generic class defaults — so this step's manual lookup is belt-and-suspenders for your own reporting to the user, not load-bearing for what the script actually does.

## 2. Determine the polymer class

- Prefer the `classify_polymer` MCP tool (`mcp-mol-builder-server`) if connected this session.
- Otherwise reason from the repeat-unit SMILES against `guides/polymer_rules.json`'s `classes` (PHYC, PSTR, PVNL, PACR, PHAL, PDIE, POXI, PSUL, PEST, PAMD, PURT, PURA, PIMD, PANH, PCBN, PIMN, PSIL, PPHS, PKTN, PSFO, PPNL). No good fit → say so explicitly rather than forcing a match.

## 3. Generate the decision scaffold

Run once, before any annotation begins:

```bash
python3 orchestration/scripts/make_decision_scaffold.py \
  --run_name <name> --polymer_class <CLASS> --smiles '<smiles>' --properties <props>
```

This deterministically writes `data/<run_name>/raw/decision.json`, pre-populated from `<CLASS>`'s current defaults in `guides/polymer_rules.json`: one row per pre-simulation policy, each carrying a `default_choice`, `criteria_evaluated`, and any evidence already transcribable from the class entry. Top-level `rationale` is left `[]` and `confidence` left `"unreviewed"` — both are deliberately invalid and block materialization (step 6) until you replace them with real reasoning.

`D-05_convergence`, `D-06_tg_fit_quality`, and `D-07_property_method` have no row here — `decision_policy.json` defines all three as mechanized runtime gate verdicts (`equil_verdict`, `tg_gate_verdict`, `bm_gate_verdict`) to route on, not pre-simulation choices to reason about now.

This step runs **exactly once** per run. Re-running it requires `--force` and destroys any annotation already written — never re-run it as part of step 6's fix loop; re-run `--dry-run` there instead.

## 4. Ground in literature

This skill only proceeds past step 1 in `reasoned` mode (novel / not yet `protocol_validated` for
the requested properties), so this step always fires — no coverage judgment call needed.

Launch both literature-grounding agents **in parallel** (single message, two `Agent` calls):
- `Agent(subagent_type="ff-protocol-literature-worker", ...)` — `polymer_name` (if resolved),
  `polymer_class`, `smiles`, `properties_requested`,
  `output_path: data/<run_name>/raw/literature_grounding_ff_protocol.json`
- `Agent(subagent_type="system-size-literature-worker", ...)` — same inputs,
  `output_path: data/<run_name>/raw/literature_grounding_system_size.json`

Wait for both `RESULT:` blocks, then read both JSON files. Each is DOI-verified, MD-simulation-study-only
evidence — advisory only, consumed in step 5 below. If either worker reports `error:` (all searches
failed or it couldn't write its file), proceed with `polymer_rules.json` defaults only and note the
gap in step 5's `dominant_uncertainty` — never block this skill on a literature-search failure.

## 5. Annotate the scaffold, row by row, grounded in literature

Open `data/<run_name>/raw/decision.json`. For each of the 5 `decision_evaluations` keys, read `orchestration/decision_policy.json['policies']`'s matching policy (`hardware`, `forcefield`, `charges`, `electrostatics`, `system_size`) — its `evaluate`/`require`/`rationale`/`evidence_required`/`default_source` fields — compare the shown `default_choice` against a genuine judgment, and update the row in place.

`default_choice` is **read-only provenance**, not something you edit: `materialize_plan()` only reads `criteria_evaluated`/`evidence`/`alternatives` off each row, so changing `default_choice` has no effect. To disagree with a shown default, add the corresponding key to top-level `overrides` (see the allowlist below) and leave `default_choice` as-is — it documents what the class defaulted to, for provenance.

**For `evidence_required: true` policies** (currently `D-01_ff`, `D-03_electrostatics`): first check step 4's `literature_grounding_ff_protocol.json`. Transcribe each `verified: true` source backing `forcefield`/`electrostatics` into the row's `evidence` array as `{"claim": <source.claim>, "source_doi": <source.doi>, "citation": <source.title>}` — this satisfies validation (`validate_run_plan.py` requires `source_doi`/`citation`). If that field's grounding confidence is `low` or empty, fall back to `polymer_rules.json`'s per-class `citations`/`ff_justification_doi`/`notes` as before (the seeded `evidence` entries use a bare `"source"` key and are placeholders — they do **not** satisfy validation on their own), and note the gap in `dominant_uncertainty`.

**For `D-04_system_size`**: check step 4's `literature_grounding_system_size.json`. When `dp_typical`/`nchain` are grounded (non-null, evidence-backed) and disagree with the class default, set `overrides.dp_typical`/`overrides.nchain` accordingly (both are valid override keys — see the allowlist below) and record the convergence evidence (`convergence_basis`, sources) in the row's `evidence`/`criteria_evaluated`. Low/empty confidence → reason from `polymer_rules.json`'s class defaults as before.

**For `cte_glass_melt`** (from `literature_grounding_ff_protocol.json`): when `alpha_glass_per_K`/`alpha_melt_per_K` are grounded with `verified: true` sources, set `overrides.alpha_glass_per_K`/`overrides.alpha_melt_per_K`.

**Never fabricate an experimental value for this SMILES.** Don't set `overrides.experimental_tg_K` / `experimental_density_gcm3` / `exp_K_min_GPa` / `exp_K_max_GPa` from a guess, a WebSearch, or step 4's grounded `density_target_gcm3`/`tg_target_K` for a genuinely novel polymer — leave them unset. Those two grounded fields are an MD study's own cited validation target, not verified experimental ground truth; they only inform `dominant_uncertainty`/rationale narrative (e.g. does the cited target roughly match this class's already-curated experimental value, if any) and the FF confidence judgment above — never an `overrides.experimental_*` value. This is safe by design:
- **Density and K unset → `None`**: both degrade gracefully everywhere they're checked (no error, no block) — `exp_K_GPa` is a final-report grading target only. One side effect worth knowing: an unset density also skips `inspect_data_file`'s pre-build finite-size forecast; accepted for an unvalidated system with nothing curated to check against.
- **Tg resolves and drives regime automatically — don't override it.** A class/member with no curated Tg falls back to a group-contribution estimate, which also decides glassy-vs-rubbery regime, defaulting glassy when that estimate is uncertain (padded by its own ±80K accuracy before the 300K cutoff). Override `T_workflow_K`/`T_equil_K` directly only if you have a specific reason to disagree with the resolved regime.
- **Exception: pin a known member's already-curated value.** If you've identified which member this SMILES is, pin it via `overrides.experimental_tg_K` / `experimental_density_gcm3` / `exp_K_min_GPa` / `exp_K_max_GPa` with real curated data.

**Stay inside the override allowlist.** Only keys in `orchestration/scripts/scientific_control.py`'s `OVERRIDE_RANGES` / `ENUM_OVERRIDES` / `SEQUENCE_OVERRIDES` / `BOOLEAN_OVERRIDES` are settable via `overrides` — read that file directly for the current keys and each numeric key's validated range; this doc must not hand-duplicate a list that drifts out of sync with the code. Never set paths, commands, filenames, templates, or raw LAMMPS content — those stay code-owned. An override outside the allowlist or out of range is rejected by validation.

**Fill the top-level fields**: replace `rationale: []` with real reasoning (non-empty, or materialization is blocked); fill `assumptions`; set `dominant_uncertainty` to one short name; replace `confidence: "unreviewed"` with `low`/`medium`/`high`.

## 6. Materialize, preview, and self-review — never execute yet

```bash
python3 orchestration/scripts/scientific_control.py \
  --run-name <name> --goal '<the user's stated scientific goal>' --smiles '<smiles>' \
  --properties <comma-separated> --polymer-class-hint <CLASS> \
  --decision-file data/<name>/raw/decision.json --dry-run
```

This validates the decision, materializes `run_plan.json`, and resolves every stage's parameters without submitting anything. The decision file already exists from step 3 — this step never writes it, only reads and validates it. If validation fails, fix `data/<name>/raw/decision.json` in place and re-run this command; do **not** re-run `make_decision_scaffold.py`. Note that override validity itself (allowlist membership, type, numeric range) was already checked earlier, inside `scientific_control.py`, before this command ever materializes anything — a finding reported here is always a `decided_params`/`decisions`/`planned_stages` structural issue (criteria coverage, evidence presence, stage schema), never a rejected override.

**Read the resolved output back and check it against your own reasoning** — the dry-run's `result` is what actually reaches the simulation, not the `default_choice` values you read in step 5, and a divergence can happen silently. Fix any mismatch with `overrides`, re-run `--dry-run`, and confirm it landed before reporting. Only override a key you have reasoned evidence for.

## 7. Report and hand off

Summarize: class + why, properties, overrides + rationale (including any set during step 6's self-review, and why), which `evidence_required` policies were literature-grounded (with DOI) vs. fell back to `polymer_rules.json` vs. genuinely ungrounded, dominant uncertainty + confidence, dry-run stage output. Flag anything `scientific_control.py`/`validate_run_plan.py` rejected and fix the decision file before retrying.

**Only drop `--dry-run` after the user explicitly confirms** — it submits real jobs and claims GPU resources. Give the user this exact command to run when ready:

```bash
python3 orchestration/scripts/scientific_control.py \
  --run-name <name> --goal '<the user's stated scientific goal>' --smiles '<smiles>' \
  --properties <comma-separated> --polymer-class-hint <CLASS> \
  --decision-file data/<name>/raw/decision.json
```
