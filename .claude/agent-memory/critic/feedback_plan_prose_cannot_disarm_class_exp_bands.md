---
name: plan-prose-cannot-disarm-class-exp-bands
description: A plan note saying "do NOT grade against polymer_rules exp_K_GPa/exp_density" is inert — gen_prompt._exp_K_range/_exp_density_range read the plan-overlaid class dict, so only a decided_params key can override a class band
metadata:
  type: feedback
---

`gen_prompt.apply_plan` builds `effective = {**cls, **plan["decided_params"]}` (gen_prompt.py:129)
and every exp-band helper reads that dict:

- `_exp_K_range(cls)` -> `cls["exp_K_GPa"]`, returns `[min,max]` or `[None,None]`
- `_exp_density_point/_exp_density_range(cls)` -> `cls["experimental_density_gcm3"]` (scalar -> +/-5%)

So a class band is overridable ONLY by a `decided_params` key of the same name. Prose in
`assumptions[]` or `planned_stages[].success_criteria.note` reaches no worker prompt
([[plan-annotations-never-reach-workers]]).

**Why:** PLA1 round 1 (2026-08-14). The plan correctly identified that
`polymer_rules.json:PEST.exp_K_GPa {3.0,4.5}` is PET/PBT Young's-modulus-derived and said in two
places it must not grade PLA (archived PLA Murnaghan K 4.46-5.39 -> FAIL-high). Nothing armed it:
`decided_params` carried no `exp_K_GPa`, and `SUMMARY.md:19-20,28-30` OMITS the
`--exp_K_min/--exp_K_max` CLI override when the Phase-C exp-lookup returns null, deliberately
falling back to the class band. Density was fine in the same plan only because the planner DID set
`decided_params.experimental_density_gcm3 = 1.248`.

**How to apply:** whenever a plan argues a class exp band is wrong for this member/SMILES, check
`decided_params` for the matching key before accepting it. Missing key = BLOCKING finding. State
the requirement (the wrong band must not reach the helper) rather than prescribing `null` — commit
83e28eb turned omitted values into errors, so a null may hard-fail instead of disarming; make the
planner verify its chosen form through `gen_prompt --stage run-summary --plan`.

**Round-2 outcome (verified, so reuse it):** `exp_K_GPa: null` IS the correct disarm and does not
hard-fail. An explicit null key shadows the class value in the `{**cls, **decided_params}` merge
(check `has("exp_K_GPa")` — present-and-null, not absent); `_exp_K_range`'s `isinstance(exp, dict)`
guard fails and line 295 returns `[None,None]` unconditionally; `run-summary-worker.md:34` already
says "Pass exp_K_min/max only if both non-null (omit if either is null)", so the pair is omitted
rather than passed; `generate_run_summary.py:279-282` yields `K_status="no exp ref"` and
`_floor_band(None)` short-circuits at line 213-214. 83e28eb's omitted-value-is-an-error rule bites
protocol args (`velocity_seed`, engine), NOT these exp-reference pairs, which have an explicit
omit-if-null contract. The DB path is untouched by the null: `gen_prompt.py:1263-1277` ranks
CLI > non-degenerate DB range > class, and `_k_from_db` never reads `cls` — so a real PLA-specific
measurement still grades, and only the class band is removed. Also confirm the analyze-bm side is
inert: `exp_K_range` is printed at gen_prompt.py:1203 but no `exp_K` arg exists in
analyze-bm-worker.md / BULK_MODULUS.md / MURNAGHAN.md.

**Codebase friction worth fixing (not yet filed):** the two `enforce_gate.py` paths disagree on
where the exp density comes from. `enforce_live` takes `--exp-density-gcm3` (fed from the
plan-overlaid dict, so a `decided_params` pin works) and sets `gates["density_in_band"]` at line
319. The retrospective path (`enforce_gate.py <run_name>`) reads
`cls_rules.get("experimental_density_gcm3")` from polymer_rules ONLY (line 212) — it already
consults the plan for `dp_typical` at line 205, so the plan is in hand and just isn't asked. For a
class with no class-level key (PEST), `density_in_band` silently becomes `None` and is dropped by
the `v is not None` filter, and `density_value_binding` never fires. A post-hoc audit therefore
reports a quieter gate set than the live run enforced. One-line fix: `dp.get(
"experimental_density_gcm3") or cls_rules.get("experimental_density_gcm3")`.

Related: [[success-criteria-contradict-the-gating-path]], [[critic-scope-blocks-default-source-checks]], [[grep-repo-root-beats-blocked-paths]]
