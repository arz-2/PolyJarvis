---
name: novel-run-plan
description: Act as PolyJarvis's scientific planning agent to produce a run_plan.json for a polymer SMILES that is not yet protocol_validated (novel or partially-validated) — reasons each decision against orchestration/decision_policy.json, writes a decision file matching docs/AGENT_CONTRACT.md's schema, and materializes + dry-run-previews the plan via scientific_control.py. Use when the user wants to simulate a new polymer/SMILES not already covered by guides/system_characterization_cache.json. Never submits a real simulation itself.
---

$ARGUMENTS may give run_name, SMILES, and properties (density/tg/bulk_modulus). Ask for whatever is missing.

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

## 4. Stay inside the override allowlist

Only keys in `orchestration/scripts/scientific_control.py`'s `OVERRIDE_RANGES` / `ENUM_OVERRIDES` / `SEQUENCE_OVERRIDES` / `BOOLEAN_OVERRIDES` are settable via `overrides` — read that file directly for the current keys and each numeric key's validated range; this doc must not hand-duplicate a list that drifts out of sync with the code.

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

## 6. Materialize and preview — never execute yet

```bash
python3 orchestration/scripts/scientific_control.py \
  --run-name <name> --goal '<the user's stated scientific goal>' --smiles '<smiles>' \
  --properties <comma-separated> --polymer-class-hint <CLASS> \
  --decision-file data/<name>/raw/decision.json --dry-run
```

This validates the decision, materializes `run_plan.json`, and resolves every stage's parameters without submitting anything.

## 7. Report and hand off

Summarize: class + why, properties, overrides + rationale, any literature gaps found or unresolved, dominant uncertainty + confidence, dry-run stage output. Flag anything `scientific_control.py`/`validate_run_plan.py` rejected and fix the decision file before retrying.

**Only drop `--dry-run` after the user explicitly confirms** — it submits real jobs and claims GPU resources.
