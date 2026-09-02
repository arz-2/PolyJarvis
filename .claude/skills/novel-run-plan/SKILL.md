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

- Canonicalize: `python3 orchestration/scripts/rules_common.py canon '<smiles>'`
- Look up the canonical SMILES in `guides/system_characterization_cache.json`.
  - `protocol_validated: true` AND `validated_properties` covers every requested property → **not novel**: stop, use `python3 orchestration/scripts/make_deterministic_plan.py run-plan --run_name <name> --polymer_class <CLASS> --smiles '<smiles>' --properties <props>` instead.
  - Otherwise → `decision_policy.json`'s `confidence_gate.novel_or_partially_validated`: `plan_mode = reasoned`. Every decision below needs real reasoning and evidence, not a fast-path guess.

`make_deterministic_plan.py` performs this same canonicalize-and-lookup check itself once `--smiles` is passed (`make_plan_from_cache`), replaying the exact frozen protocol a prior completed campaign for this SMILES validated rather than generic class defaults — so this step's manual lookup is belt-and-suspenders for your own reporting to the user, not load-bearing for what the script actually does.

## 2. Determine the polymer class

- Prefer the `classify_polymer` MCP tool (`mcp-mol-builder-server`) if connected this session.
- Otherwise reason from the repeat-unit SMILES against `guides/polymer_rules.json`'s `classes` (PHYC, PSTR, PVNL, PACR, PHAL, PDIE, POXI, PSUL, PEST, PAMD, PURT, PURA, PIMD, PANH, PCBN, PIMN, PSIL, PPHS, PKTN, PSFO, PPNL). No good fit → say so explicitly rather than forcing a match.

## 3. Generate the decision

Run once, before any critique begins:

```bash
python3 orchestration/scripts/make_deterministic_plan.py decision \
  --run_name <name> --polymer_class <CLASS> --smiles '<smiles>' --properties <props>
```

This deterministically writes `data/<run_name>/raw/decision.json` — **complete, not a scaffold**.
Every row is resolved from this repo's own resolvers (`solve_system_size` for D-04,
`select_hardware` for D-08, `polymer_rules.json`'s `electrostatics_decision_guide` and its
`_metadata.primary_sources` citation records for D-01/D-02/D-03), and every criterion the
matching policy in `decision_policy.json` names gets its own evidence entry — including the
criteria this layer honestly cannot reach, which say `NOT MEASURED` / `NOT ASSESSABLE` rather
than going silent. `rationale` is written for you. `--smiles` is required: all five decisions
are resolved per-molecule now, not per-class.

`confidence` comes back `"unreviewed"`, which is invalid — it is the **only** thing blocking
materialization, and step 5 is where you replace it. (`--baseline` stamps `"low"` instead, for
the deterministic benchmark arm that runs with no LLM in the loop; a normal reasoned run leaves
it off.)

`D-05_convergence`, `D-06_tg_fit_quality`, and `D-07_property_method` have no row here —
`decision_policy.json` defines all three as mechanized runtime gate verdicts (`equil_verdict`,
`tg_gate_verdict`, `bm_gate_verdict`) to route on, not pre-simulation choices.

This step runs **exactly once** per run. Re-running it requires `--force` and destroys any
critique already applied — never re-run it as part of step 6's fix loop; re-run `--dry-run` there
instead.

## 4. Critique the decision against published MD literature

This skill only proceeds past step 1 in `reasoned` mode (novel / not yet `protocol_validated` for
the requested properties), so this step always fires.

Launch the critic:

- `Agent(subagent_type="literature-grounding-worker", ...)` — `polymer_name` (if resolved),
  `polymer_class`, `smiles`, `properties_requested`,
  `decision_path: data/<run_name>/raw/decision.json`,
  `output_path: data/<run_name>/raw/literature_grounding.json`

It reads the decision you just generated, mines `db/polydatabase_md.sqlite` (an LLM-mined index
of published MD studies: force field, ensemble, T/P, and the density/Tg/Rg/modulus each one
reported) plus its own persistent evidence store, falls back to DOI-verified WebSearch, and
returns an agree/disagree verdict on `D-01_ff`, `D-02_charges` and `D-03_electrostatics` — the
three rows literature can actually speak to. `D-04_system_size` and `D-08_hardware` are out of
scope: the cell is derived deterministically from this SMILES's system-mass floor, and hardware
is a property of this host.

Wait for its `RESULT:` block, then read `literature_grounding.json`. It is advisory only. If the
worker reports `error:`, proceed with the tool's deterministic decision unchanged and say so in
step 5's `dominant_uncertainty` — never block this skill on a literature-search failure.

## 5. Apply the critique, then sign off

You are no longer authoring rows — you are adjudicating a critique. Open
`data/<run_name>/raw/decision.json` and `data/<run_name>/raw/literature_grounding.json`.

**For each entry in the critic's `critique{}`:**

- `verdict: "agrees"` or `"no_evidence"` → nothing to do. The tool's choice stands.
- `verdict: "disagrees"` → decide. Either apply its `suggested_override` by adding that key to
  top-level `overrides`, or leave the tool's choice and record why you declined in `rationale`.
  Weigh the critic's `confidence` and `supporting_dois` against what the tool's own evidence
  entry already said; a `disagrees` backed only by a `class_representative` analog lead is weak.

**Transcribe the sources you acted on.** For any row where the critic's evidence changed your
mind or materially strengthens the case, append to that row's `evidence` array:
`{"claim": <source.claim>, "source_doi": <source.doi>, "citation": <study.title>, "origin": "critic"}`.
The `origin: "critic"` tag is load-bearing: `benchmarks/.../metrics/llm_contribution.py` counts
only critic-tagged cited evidence as LLM contribution, and treats the tool's own
`origin: "autofill"` entries as the deterministic baseline. Never delete or retag an autofill
entry.

**`default_choice` stays read-only.** `materialize_plan()` reads only
`criteria_evaluated`/`evidence`/`alternatives` off each row, so editing `default_choice` has no
effect. Disagree via `overrides`.

**Stay inside the override allowlist.** Only keys in `orchestration/scripts/scientific_control.py`'s
`OVERRIDE_RANGES` / `ENUM_OVERRIDES` / `SEQUENCE_OVERRIDES` / `BOOLEAN_OVERRIDES` are settable —
read that file directly for the current keys and each numeric key's validated range. Never set
paths, commands, filenames, templates, or raw LAMMPS content. An override outside the allowlist
or out of range is rejected by validation.

**Never fabricate an experimental value for this SMILES.** Don't set
`overrides.experimental_tg_K` / `experimental_density_gcm3` / `exp_K_min_GPa` / `exp_K_max_GPa`
from a guess, a WebSearch, or the critic's `tg_target_K` for a genuinely novel polymer — leave
them unset. `tg_target_K` is an MD study's own cited validation target, not verified experimental
ground truth; it informs your `dominant_uncertainty` narrative and the FF confidence judgement,
never an `overrides.experimental_*` value. This is safe by design:
- **Density and K unset → `None`**: both degrade gracefully everywhere they're checked (no error,
  no block) — `exp_K_GPa` is a final-report grading target only. One side effect worth knowing:
  an unset density also skips `inspect_data_file`'s pre-build finite-size forecast; accepted for
  an unvalidated system with nothing curated to check against.
- **Tg resolves and drives regime automatically — don't override it.** A class/member with no
  curated Tg falls back to a group-contribution estimate, which also decides glassy-vs-rubbery
  regime, defaulting glassy when that estimate is uncertain (padded by its own ±80K accuracy
  before the 300K cutoff). Override `T_workflow_K`/`T_equil_K` directly only if you have a
  specific reason to disagree with the resolved regime.
- **Exception: pin a known member's already-curated value.** If you've identified which member
  this SMILES is, pin it via `overrides.experimental_tg_K` / `experimental_density_gcm3` /
  `exp_K_min_GPa` / `exp_K_max_GPa` with real curated data.

**Then sign off.** Append your adjudication reasoning to `rationale` (don't replace what the tool
wrote — it is the provenance of every deterministic choice), add any `assumptions` the critique
raised, set `dominant_uncertainty` if the critique changed which gap matters most, and replace
`confidence: "unreviewed"` with `low`/`medium`/`high`. **That last edit is the only thing
standing between this file and execution** — deleting the key does not skip the gate.

## 6. Materialize, preview, and self-review — never execute yet

```bash
python3 orchestration/scripts/scientific_control.py \
  --run-name <name> --goal '<the user's stated scientific goal>' --smiles '<smiles>' \
  --properties <comma-separated> --polymer-class-hint <CLASS> \
  --decision-file data/<name>/raw/decision.json --dry-run
```

This validates the decision, materializes `run_plan.json`, and resolves every stage's parameters without submitting anything. The decision file already exists from step 3 — this step never writes it, only reads and validates it. If validation fails, fix `data/<name>/raw/decision.json` in place and re-run this command; do **not** re-run `make_deterministic_plan.py decision`. Note that override validity itself (allowlist membership, type, numeric range) was already checked earlier, inside `scientific_control.py`, before this command ever materializes anything — a finding reported here is always a `decided_params`/`decisions`/`planned_stages` structural issue (criteria coverage, evidence presence, stage schema), never a rejected override.

**Read the resolved output back and check it against your own reasoning** — the dry-run's `result` is what actually reaches the simulation, not the `default_choice` values you read in step 5, and a divergence can happen silently. Fix any mismatch with `overrides`, re-run `--dry-run`, and confirm it landed before reporting. Only override a key you have reasoned evidence for.

## 7. Report and hand off

Summarize: class + why, properties, overrides + rationale (including any set during step 6's self-review, and why), for each of D-01/D-02/D-03: what the tool decided and on what evidence, what the critic's verdict was, and whether you applied or declined its override (three buckets: autofilled-and-confirmed, autofilled-and-overridden, autofilled-and-unchallenged), dominant uncertainty + confidence, dry-run stage output. Flag anything `scientific_control.py`/`validate_run_plan.py` rejected and fix the decision file before retrying.

**Only drop `--dry-run` after the user explicitly confirms** — it submits real jobs and claims GPU resources. Give the user this exact command to run when ready:

```bash
python3 orchestration/scripts/scientific_control.py \
  --run-name <name> --goal '<the user's stated scientific goal>' --smiles '<smiles>' \
  --properties <comma-separated> --polymer-class-hint <CLASS> \
  --decision-file data/<name>/raw/decision.json
```
