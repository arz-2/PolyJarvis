---
name: critic-scope-blocks-default-source-checks
description: The per-agent context hook denies the critic Read AND Bash on guides/polymer_rules.json and guides/MURNAGHAN.md, and allowlists only canon_smiles.py + validate_run_plan.py — so default_source claims cannot be verified; record them as unverified-by-critic instead of assuming
metadata:
  type: feedback
---

The critic's context boundary denies **both** `Read` and `Bash` on `guides/polymer_rules.json`
and `guides/MURNAGHAN.md`, and `orchestration/decision_policy.json` is reachable only via `Read`
(Bash/`jq` on it is denied). Only `canon_smiles.py` and `validate_run_plan.py` are on the critic's
Bash allowlist — `make_deterministic_plan.py` and `select_hardware.py` are **not**, so there is no
indirect route to surface class defaults either.

**Why:** critic.md step 2 asks for judgment on `require` clauses and evidence whose
`default_source` is `polymer_rules.json:classes.<CLASS>.*`. With the file unreadable, every such
claim is transcription-checked for internal consistency only. Silently accepting them would be a
rubber stamp; bouncing the plan for them would be a boilerplate bounce the planner cannot fix
(the planner *could* read the file; the critic cannot).

**How to apply:** when a decision's evidence terminates in `polymer_rules.json` or
`MURNAGHAN.md`, cross-check it against (a) `decision_policy.json`, (b) the plan's own internal
consistency, (c) `data/<RUN>/raw/literature_grounding.json` — **the partial workaround**: the
grounding writer's `notes` field routinely transcribes the current class defaults verbatim
("Planner should fall back to polymer_rules.json PKTN class defaults (already well-populated:
PCFF/pppm/dp_typical=32/nchain=8, tg_rates=[25,50,100], alpha_melt_per_K=6.69e-4,
exp_K_GPa=[4.0,5.8])"), which independently *corroborates* those keys — and (d) the campaign
record in the user-level memory index (e.g. the PDIE ladder widening, the PHYC/PDIE 500 ps/T rate
floor). Split the advisory: name the keys corroborated by grounding separately from the ones
corroborated nowhere (on PEEK1 those were `exp_K_GPa` provenance `Chen2025; Sahputra2018` and the
`exp_density_note` amorphous comparator), and attach a concrete downstream check to the
uncorroborated ones. Grounding also settles staleness disputes: a user-memory ladder
recommendation that disagrees with the grounding-quoted class value is the stale one — don't
bounce on it. Do not claim to have verified a file you could not open, and do not escalate on it
alone.

Related: [[feedback-blocked-probe-is-not-a-plan-inconsistency]]
