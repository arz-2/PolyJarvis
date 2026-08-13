---
name: pktn-reasoned-plan
description: How to build a PKTN (polyetherketone / PEEK) reasoned run_plan — amorphous-vs-semicrystalline density comparator trap, slowest_rate Tg fallback, glassy Murnaghan with no class bm_pressures_atm, dominant under-annealing uncertainty
metadata:
  type: feedback
  ingested_at: 2026-08-11
---

PKTN is in-table with class-specific temperatures (T_equil=770, anneal 850/**12** cycles, t_equil=15 ns, Tg sweep 250-750 K @ 20 K, rates [25,50,100], dp_typical=32, nchain=8 => ~9,216 atoms). Skip `estimate_tg_group_contribution.py` (in-table). PCFF/EMC/pppm.

**Why:** each new SMILES earns one reasoned pass; PKTN carries three class-specific traps that a verbatim transcription of class defaults gets wrong.

**How to apply:**
- **Density comparator trap (the big one).** Grounding (PEEK2020, 10.3390/polym12051054, `verified:true`) returns `density_target_gcm3 = 1.328` — that is the **semicrystalline** value. The amorphous MD comparator is **1.263** (`PKTN.experimental_density_gcm3` + `exp_density_note`). Reject 1.328 as a **phase mismatch**, explicitly NOT as a verification failure (the source is verified) — mislabeling the reason is what the critic catches. Using 1.32 previously produced a false -9%.
- **Member pin:** `experimental_tg_K` is an object {PEEK:418, PEK:440, PEKK:433}; ether-ether-ketone SMILES => PEEK 418 K. Dict median is 433 — state that both exceed 300 K so `is_glassy` is unaffected *by coincidence*, don't rely on it.
- **D-06 ladder:** keep `[25,50,100]` and **preserve `tg_slope_gate_fallback:"slowest_rate"`** — slope-gate FAIL is structural for rigid aromatics (cold-start staircase inverts the rate trend; seed rerolls cannot fix it). Swept rate is therefore rates[0]=25 K/ns => 20/(25*1*1e-6)=800,000 steps/800 ps per bin, 20 ns total. Note the highest rate (100) is **exactly at** the 200,000-step floor, not clear of it.
- **D-07 / bm_pressures_atm:** PKTN has none, and that is CORRECT here — the "add [1,500,1000,2000,5000]" lesson in [[phal-reasoned-plan]] applies only to the *rubbery* fall-through to fluctuation-only. PEEK is glassy (418>>300), the scaffold already emits `murnaghan` with `chain_submitted:true`, and the glassy fallback ladder [-1000,0,3000,7000,15000] is documented in `decision_policy.json:policies.property_method.rationale` — cite that, not MURNAGHAN.md (planner has no read access to guides/). Both grounding `bulk_modulus_notes` sources are `verified:false` (paywalled) => cite neither; use `exp_K_GPa [4.0,5.8]` with its non-MD PVT provenance stated.
- **Dominant uncertainty = `cooling_stage_under_annealing_density_deficit`**, probe `fast_density_screen`. `_eq_annealing_cycles_note` says the 8->12 raise is an **unvalidated hypothesis (n=0)** after UNDER_ANNEALED_COOLING (shortfall 0.91-0.93) on prior PKTN cells — and PEEK is named in `density_value_binding` as the `extrapolation_reliable=False` case (470 K cooling span), so pre-register `assess_cooling_contraction` + prefer `re_melt_slow_recool`; never pre-authorize the class note's "~5% underdensity is ANTICIPATED, not a failure" as acceptance. Attribute all of this to the class block you read, not to PEEK1-4 run artifacts ([[feedback-dont-assert-prior-run-results-unchecked]]).
- **D-08:** `select_hardware.py` returns kokkos/1 GPU/mpi=1, `decided_params_override={}`, confidence medium (9,216 atoms outside [0.5x,2x] of the 3,020-atom pcff probe). Append one extra evidence line for live contention (GPU 0 held by a concurrent run, Sum(mpi)=2<=18) — never write a GPU index into `decided_params`.
- **Confidence labels must track grounding per field**, not per plan: grounding's `system_size` block was `confidence:low` with null dp/nchain, so D-04 is `low` even though the FF/electrostatics rows are `medium` (verified DOI). Labeling D-04 `medium` while its own evidence says "no usable anchor" is a self-contradiction a critic pulls on.
- Verify the empty-cache claim yourself (`Read guides/system_characterization_cache.json` — it was literally `{}`); don't relay the orchestrator's "not validated" statement as your own verified fact in `assumptions`.
- Result: `validate_run_plan.py` returned 0 findings on the first try with D-01..D-08 all present, non-empty `alternatives` everywhere (D-03's single alternative stated as "precluded by require"), and `t_range_brackets_exp_tg:true` + `exp_tg_K:418` on the tg stage.

See [[psfo-reasoned-plan]] (sibling rigid-aromatic PCFF class, same slowest_rate fallback) and [[phal-reasoned-plan]].
