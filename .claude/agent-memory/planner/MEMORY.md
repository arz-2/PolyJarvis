# Planner Agent Memory Index

- [PSTR reasoned plan](pstr_reasoned_plan.md) — polystyrenics reasoned-plan lessons (FF/pppm/glassy-K/hardware/Tg-ladder) [ingested 2026-06-25]
- [PVNL reasoned plan](pvnl_reasoned_plan.md) — polyvinyls (esp. PVC) reasoned-plan: FF/pppm/glassy-K/hardware + Tg-ladder slope-gate fix (widen to 1.2 dec) [ingested 2026-06-25]
- [PSFO reasoned plan](psfo_reasoned_plan.md) — polysulfones (PSU/PES/PPSU) reasoned-plan: member-by-SMILES, PCFF/pppm/glassy-K, >10k-atom cell still 1 GPU [ingested 2026-06-25]
- [Don't assert prior-run results unchecked](feedback_dont_assert_prior_run_results_unchecked.md) — never cite a sibling run's ladder/slope_gate_pass in evidence without jq-verifying; PSU4 claim about PSU1/PSU2 was false [2026-06-26]
- [PHAL reasoned plan](phal_reasoned_plan.md) — polyhalogenated (PVDF *CC(F)(F)*): rubbery-at-300K Tg ambiguity, missing class bm_pressures_atm/exp_K_GPa (add PHYC/PDIE convention), grounding-invalidated ff_justification_doi handling [ingested 2026-08-05]
- [PDIE reasoned plan](pdie_reasoned_plan.md) — cis-1,4-PBD: exp_K_GPa [1.38,1.95] is a two-member span (mis-grades K), 404 Sharma2016 DOI, rubbery equil gate, Tg floor at equality [2026-08-11]
- [PKTN reasoned plan](pktn_reasoned_plan.md) — PEEK: 1.328 grounded density is SEMICRYSTALLINE (use 1.263, phase mismatch not verification), slowest_rate Tg fallback, glassy Murnaghan w/o class pressures, under-annealing dominant [2026-08-11]
- [Plan edit hygiene](feedback_plan_edit_hygiene.md) — deleting a JSON array element via Edit left a trailing comma (validator crash); read MEMORY.md before writing a new memory file [2026-08-11]
- [Planner scope denials](planner_scope_denials.md) — Bash jq on guides/*.json, Read on MURNAGHAN.md/THERMAL_TRACK.md, Bash gen_prompt.py all blocked; Read polymer_rules.json instead, class-entry line map [2026-08-11, updated]
- [Rung-3 re-plan: reason, don't mechanically FF-swap](feedback_rung3_nonff_protocol_reasoning.md) — PMMA1 quench-rate-limited density: verify a fix addresses the diagnosed defect before authoring it; eq_annealing_cycles is planning-only, not a runtime lever [2026-08-11]
- [INCIDENT: memory file overwritten without Read](feedback_murnaghan_glassy_vs_rubbery_null_ladder.md) — original content lost (untracked file, no git history); ALWAYS Read before Write even for a new-seeming filename [2026-08-11]
