# Planner Agent Memory Index

- [PSTR reasoned plan](pstr_reasoned_plan.md) — polystyrenics reasoned-plan lessons (FF/pppm/glassy-K/hardware/Tg-ladder) [ingested 2026-06-25]
- [PVNL reasoned plan](pvnl_reasoned_plan.md) — polyvinyls (esp. PVC) reasoned-plan: FF/pppm/glassy-K/hardware + Tg-ladder slope-gate fix (widen to 1.2 dec) [ingested 2026-06-25]
- [PSFO reasoned plan](psfo_reasoned_plan.md) — polysulfones (PSU/PES/PPSU) reasoned-plan: member-by-SMILES, PCFF/pppm/glassy-K, >10k-atom cell still 1 GPU [ingested 2026-06-25]
- [Don't assert prior-run results unchecked](feedback_dont_assert_prior_run_results_unchecked.md) — never cite a sibling run's ladder/slope_gate_pass in evidence without jq-verifying; PSU4 claim about PSU1/PSU2 was false [2026-06-26]
- [PHAL reasoned plan](phal_reasoned_plan.md) — polyhalogenated (PVDF *CC(F)(F)*): rubbery-at-300K Tg ambiguity, missing class bm_pressures_atm/exp_K_GPa (add PHYC/PDIE convention), grounding-invalidated ff_justification_doi handling [ingested 2026-08-05]
- [PKTN reasoned plan](pktn_reasoned_plan.md) — PEEK: 1.328 grounded density is SEMICRYSTALLINE (use 1.263, phase mismatch not verification), slowest_rate Tg fallback, glassy Murnaghan w/o class pressures, under-annealing dominant [2026-08-11]
- [Plan edit hygiene](feedback_plan_edit_hygiene.md) — Edit-deleted array element left a trailing comma (validator crash); validator wants the exact key `exp_tg_K`; read MEMORY.md first [2026-08-14]
- [Grounding vs rules conflicts](feedback_grounding_vs_rules_conflicts.md) — verified:false targets, wrong notes_only charges, null CTE ≠ delete class alphas; literature_anchor is spent once grounded [2026-08-13]
- [Glassy stage criteria + unknobbed instructions](feedback_glassy_stage_criteria_and_unknobbed_instructions.md) — never assert overall_pass on equil for ct_gate_reliable=false; equil_verdict PASS is compatible; no dump knob on run_bulk_modulus_series [2026-08-13]
