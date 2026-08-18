---
name: novel-run-plan
description: Act as PolyJarvis's scientific planning agent to produce a run_plan.json for a polymer SMILES that is not yet protocol_validated (novel or partially-validated) — reasons each decision against orchestration/decision_policy.json, writes a decision file matching docs/AGENT_CONTRACT.md's schema, and materializes + dry-run-previews the plan via scientific_control.py. Use when the user wants to simulate a new polymer/SMILES not already covered by guides/system_characterization_cache.json. Never submits a real simulation itself.
---

This skill takes three arguments, parsed from $ARGUMENTS:
- `run_name` — identifier for this run (used as `data/<run_name>/`)
- `smiles` — the repeat-unit SMILES string, with exactly two `*` chain-end connection points
- `properties` — comma-separated subset of `density`, `tg`, `bulk_modulus`

State which of the three were parsed from $ARGUMENTS and which are missing, then ask the user to fill in whatever is missing before proceeding.

## 1. Determine novelty

- Canonicalize: `python3 orchestration/scripts/canon_smiles.py '<smiles>'` (radonpy env by default; `--env <env>` if renamed).
- Look up the canonical SMILES in `guides/system_characterization_cache.json`.
  - `protocol_validated: true` AND `validated_properties` covers every requested property → **not novel**: stop, use `python3 orchestration/scripts/make_deterministic_plan.py --run_name <name> --polymer_class <CLASS> --smiles '<smiles>' --properties <props>` instead (code emits the plan directly, no reasoning needed).
  - Otherwise → `decision_policy.json`'s `confidence_gate.novel_or_partially_validated`: `plan_mode = reasoned`. Every decision below needs real reasoning and evidence, not a fast-path guess.

## 2. Determine the polymer class

- Prefer the `classify_polymer` MCP tool (`mcp-mol-builder-server`) if connected this session.
- Otherwise reason from the repeat-unit SMILES against `guides/polymer_rules.json`'s `classes` (PHYC, PSTR, PVNL, PACR, PHAL, PDIE, POXI, PSUL, PEST, PAMD, PURT, PURA, PIMD, PANH, PCBN, PIMN, PSIL, PPHS, PKTN, PSFO, PPNL). No good fit → say so explicitly rather than forcing a match.

## 3. Reason each decision against policy, grounded in literature

Read `orchestration/decision_policy.json['policies']` — `hardware`, `forcefield`, `charges`, `electrostatics`, `system_size`, `equilibration`, `tg_protocol`, `property_method`. For each policy relevant to the requested properties, read its `evaluate`/`require`/`rationale`/`evidence_required`/`default_source` fields and form a genuine judgment. Use each policy's own `decision_id` (e.g. `D-02_charges`) as the key in `decision_evaluations`.

For `evidence_required: true` policies (currently `D-01_ff`, `D-03_electrostatics`, `D-07_property_method`): `polymer_rules.json`'s per-class `citations`/`ff_justification_doi`/`notes` are the first source. When they don't cover the exact property or member (e.g. a multi-member class's experimental reference scoped to only one member), run a real `WebSearch`, verify the citation is genuine, and record it as `decision_evaluations` evidence — never fabricate one. Nothing citable found → say so explicitly as an assumption/gap and report that property ungraded, don't skip it silently. This is the manual stand-in for `decision_policy.json`'s `uncertainty_reduction_probes.literature_anchor` (`search_ff_literature`, ROADMAP E2) — no such tool is implemented in this repo yet.

**Pin the resolved experimental targets, don't leave them to run_name matching.** `stage_params.py` resolves a multi-member class's `experimental_tg_K` / `experimental_density_gcm3` by checking whether `run_name` starts with the member key (e.g. `"PMMA2"` → `"PMMA"`) — a run_name that doesn't literally start with the member prefix (e.g. `"a-PS"` against `{"PS": 373, "P2VP": 374}`) will NOT match. For Tg this falls back to an `estimate_tg_group_contribution.py` group-contribution estimate (low confidence, ±~80K, chirality/tacticity-blind — it parses stereo SMILES fine but cannot differentiate isotactic/syndiotactic/atactic); for density there is no equivalent estimator, so an unmatched run_name resolves to `None`/a generic band instead of guessing a sibling member's real value. `exp_K_GPa` is different again: it is a flat `{min, max}` **per class, not per member** — a multi-member class's range may be scoped to only one member (check the class's own `note` field; e.g. PACR's `exp_K_GPa` note says "for glassy PMMA" even though PACR also covers PMA) and there is no matching logic to get wrong, just a range that may quietly be the wrong member's.

If step 2/3's reasoning already identifies which member this SMILES actually is (by substituent, per `D-07_property_method`'s pinning clause), or turns up a literature value via WebSearch, or accepts a group-contribution Tg estimate for a genuinely novel polymer, pin it explicitly rather than relying on run_name matching or a class default that may be scoped to the wrong member: `overrides.experimental_tg_K`, `overrides.experimental_density_gcm3`, `overrides.exp_K_min_GPa` / `overrides.exp_K_max_GPa` (see step 4). For a genuinely novel polymer with no citable experimental Tg at all, the Tg group-contribution estimate firing on its own is expected, correct behavior — only override it if you have a better number.

## 4. Stay inside the override allowlist

Only keys in `orchestration/scripts/scientific_control.py`'s `OVERRIDE_RANGES` / `ENUM_OVERRIDES` / `SEQUENCE_OVERRIDES` / `BOOLEAN_OVERRIDES` are settable via `overrides` — read that file directly for the current keys and each numeric key's validated range; this doc must not hand-duplicate a list that drifts out of sync with the code. This allowlist is exactly where a decision it has reasoned over (or a resolver mismatch it has diagnosed, like the `experimental_tg_K` case above) gets pinned into the plan — not left implicit in prose the code never reads. `overrides` values replace the class default wholesale (`apply_plan`'s `{**cls, **decided_params}`), so a scalar `overrides.experimental_tg_K` cleanly replaces a multi-member dict for this run.

Never set paths, commands, filenames, templates, or raw LAMMPS content — those stay code-owned. An override outside the allowlist or out of range is rejected by validation.

## 5. Write the decision file

Schema (see `examples/pstr_decision.json` for a filled example):

```json
{
  "polymer_class": "...",
  "properties": ["density", "tg", "bulk_modulus"],
  "rationale": ["..."],
  "overrides": {},
  "decision_evaluations": {
    "D-0N_<name>": {
      "criteria_evaluated": ["..."],
      "evidence": [{"claim": "...", "citation": "..."}],
      "alternatives": ["..."]
    }
  },
  "assumptions": ["..."],
  "dominant_uncertainty": "...",
  "confidence": "low|medium|high"
}
```

Write it to `data/<run_name>/raw/decision.json` (create the directory if it doesn't exist).

## 6. Materialize, preview, and self-review — never execute yet

```bash
python3 orchestration/scripts/scientific_control.py \
  --run-name <name> --goal '<the user's stated scientific goal>' --smiles '<smiles>' \
  --properties <comma-separated> --polymer-class-hint <CLASS> \
  --decision-file data/<name>/raw/decision.json --dry-run
```

This validates the decision, materializes `run_plan.json`, and resolves every stage's parameters without submitting anything.

**Then read the resolved output back and check it against your own reasoning, every reasoned run — not only when something happens to look wrong.** The dry-run's `result` block is what actually reaches the simulation, not the class defaults you reasoned about in the abstract in step 3 — `apply_plan`'s overlay, run_name-based member resolution, and hardware/regime derivation can all produce a resolved value that silently diverges from your intended decision. Walk the resolved `decided_params` (or the dry-run's per-stage `result`) against `decision_evaluations`/`assumptions` field by field: does `exp_tg_point_K` / `exp_density_range` / `exp_K_range` actually match the member you identified in step 3, or did run_name matching miss and silently substitute an estimate or `None`? Does `engine`/`mpi_ranks`/`gpu_per_run` match the D-08 hardware reasoning? Does `is_glassy`/`regime` match the Tg-based classification you expected? Any divergence between what you reasoned and what the plan resolved is exactly what `overrides` (step 4) exists to correct — set it, re-run this step's `--dry-run`, and confirm the fix actually landed before reporting to the user. Only override a key you have reasoned evidence for; don't override to force agreement with a guess.

## 7. Report and hand off

Summarize: class + why, properties, overrides + rationale (including any set during step 6's self-review, and why), any literature gaps found or unresolved, dominant uncertainty + confidence, dry-run stage output. Flag anything `scientific_control.py`/`validate_run_plan.py` rejected and fix the decision file before retrying.

**Only drop `--dry-run` after the user explicitly confirms** — it submits real jobs and claims GPU resources. Give the user this exact command to run when ready:

```bash
python3 orchestration/scripts/scientific_control.py \
  --run-name <name> --goal '<the user's stated scientific goal>' --smiles '<smiles>' \
  --properties <comma-separated> --polymer-class-hint <CLASS> \
  --decision-file data/<name>/raw/decision.json
```
