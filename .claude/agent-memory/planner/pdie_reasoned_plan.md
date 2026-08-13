---
name: pdie-reasoned-plan
description: PDIE (polydienes, esp. cis-1,4-PBD *C/C=C\C*) reasoned-plan lessons — rubbery-at-300K routing, two-member exp_K_GPa span that mis-grades, 404 Sharma2016 DOI, Tg floor at equality
metadata:
  type: feedback
---

Building a reasoned run_plan for PDIE / cis-1,4-PBD.

**exp_K_GPa is a TWO-MEMBER SPAN, not an uncertainty band.** `classes.PDIE.exp_K_GPa = {min:1.38, max:1.95}` reads like a band but the note attributes 1.38 GPa to cis-1,4-PBD and 1.94-1.95 GPa to cis-1,4-PI. Grading a cis-PBD run against 1.95 compares it to polyisoprene.
**Why:** the multi-member pin clause in `decision_policy.json:policies.property_method.require` names Tg/density/K explicitly, and the K half is the easiest to miss because min/max looks like a range.
**How to apply:** pin the single-member K in `assumptions[]` + D-04 + D-07 evidence (cis-PBD → Tg 174 K, density 0.90, K_T 1.38) and tell run-summary/exp-lookup not to use the other end. Same shape likely exists in other multi-member classes — check whether an exp_K_GPa min/max is a band or two members before citing it. Related: [[feedback-polymer-rules-sim-sourced-exp-bounds]].

**Rubbery routing (T_workflow 300 K >> Tg 174 K):** the scaffold's `equil` success criterion `check_equilibration_comprehensive.overall_pass: true` is unsatisfiable for a rubbery DP-100 melt — replace it with `require_rubbery` (density block-SEM <2%, homogeneity CV <25%, energy drift/SEM; reptation metrics advisory). Also state the flow through params you control (equil/anneal at T_equil 400 K → npt_production at T_workflow 300 K → Murnaghan input = that 300 K endpoint, no sub-Tg endpoint) rather than asserting stage-internal names — FOUNDATION.md is outside planner Read scope.

**bm_pressures_atm:** PDIE already carries the widened compression-only ladder `[1,1000,2500,5000,10000,15000]` plus a `bm_pressures_note` documenting two widenings (2026-06-24 after a ~24% Murnaghan-vs-fluctuation gap; ceiling 5000→15000 on 2026-08-08). Adopt it explicitly and cite the NOTE as the authority for the prior-run numbers — do not restate them as results you verified ([[feedback-dont-assert-prior-run-results-unchecked]]). The policy's two-leg PROBE protocol is scoped to classes with NO class-level ladder, so it does not apply here; say that instead of paraphrasing MURNAGHAN.md, which the planner cannot read.

**Tg ladder passes the floor AT EQUALITY:** rates [10,25,40] K/ns, dt=2 fs, step 20 K → N = 20/(40·2·1e-6) = 250,000 steps = 500 ps, exactly `tg_min_steps_per_T = 250000`. Write the arithmetic longhand AND the words "at equality" so the critic's independent recompute doesn't read it as a violation. Window 400→80 K @ 20 K = 17 bins, 5 below 174 K. No `tg_slope_gate_fallback` exists for PDIE — nothing to preserve. Cooling-rate artifact is inverted for this class (MD Tg lands at or below experiment for flexible low-fragility rubbers), so don't pad the window upward for the usual +80-120 K overestimate.

**Citation traps found this run:** (1) `classes.PDIE` cites Sharma2016 with DOI `10.1021/jp510632u`, which 404s — the correct DOI is `10.1021/acs.jpcb.5b10789`; cite only the latter. (2) The orchestrator's source-verified audit puts cis-1,4-PBD at 174 K while the grounding worker's *verified* extraction of that same paper records ~181 K as the paper's own stated target, matching `experimental_tg_K.PBD = 181`. `verified: true` certifies the RECORDED claim, so never write an evidence entry attributing 174 K to that DOI — adopt 174 as the isomer-specific comparator, record both, and note the 7 K spread changes no protocol.

**D-08:** ff_family=trappe, cell ≈ dp100 × nchain20 × 4 UA sites = 8000, outside [0.5x,2x] of the 1640-atom trappe probe cell → `select_hardware.py` returns the by_forcefield default (engine=gpu, mpi=1, 1 GPU, `neigh yes`) with empty `decided_params_override`, confidence medium. mpi=1 already sits inside the PHYC/PDIE MPI≤2 cap — do NOT bump to mpi=2; that is a non-default pin with no in-size benchmark. Add a non-dominant `hardware_optimum` uncertainty with `reduction_probe: hardware_benchmark` for the out-of-size probe cell.

**Dangling-uncertainty defect, misattributed variant:** the first draft's D-06 evidence claimed its slope-gate risk was "covered by the uncertainties[] entry `exp_tg_comparator_discrepancy`" — an entry that exists but is about the 174-vs-181 K spread, not rate span. Naming the WRONG existing uncertainty is the same blocking defect as naming a nonexistent one ([[phal-reasoned-plan]] critic round-1 precedent); fixed by adding a real `tg_rate_span_slope_gate` entry in the same edit. When a decision's evidence says "covered by uncertainty X", re-read X's own detail text and confirm it covers that specific risk.

**Two runtime footguns worth writing into the plan itself** (planner can't Read `gen_prompt.py` to check their state): (1) an orchestrator-facing `assumptions[]` line that `is_glassy=false` must be honored and overridden if `gen_prompt.py:murnaghan_prompt` still hardcodes `is_glassy=true` — otherwise the murnaghan worker hunts for a sub-Tg endpoint a rubbery plan never produces; (2) tell exp-lookup to grade K against the single member value with the standard ±5% band and NOT to emit a `min==max` override range, which is a documented false-FAIL mode.

See [[phal-reasoned-plan]] (sibling rubbery-regime + class-rules-gap pattern) and [[planner-scope-denials]].
