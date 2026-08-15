---
name: pest-reasoned-plan
description: Polyesters (PEST, member PLA *C(C)C(=O)O*) reasoned-plan facts — highest_rate convention, PET-derived exp_K band, missing class density, measured Rg for the finite-size forecast
metadata:
  type: project
---

Facts established while planning PLA1 (2026-08-14, PEST, SMILES `*C(C)C(=O)O*` → canonical `*OC(=O)C(*)C`).

**Why:** PEST is multi-member (`experimental_tg_K` is an object PET/PLA/PCL/PBT) and several of its class-level numbers are scoped to PET, not to the member being run — a plan that transcribes them unexamined mis-grades the run.

**How to apply:**
- `tg_slope_gate_fallback: "highest_rate"` is PEST's convention for the *opposite* reason to PKTN/PSFO's `slowest_rate`: stiff ester backbones DELOCALIZE at slow rates (PLA3 r25 primary 464.8 K vs alternative 360 K, slope b<0), so the highest rate gives the cleanest bilinear fit. Say this in D-06 or a Critic scanning the `tg_protocol` require clause misfires.
- `exp_K_GPa` [3.0, 4.5] is Mark2007 PET/PBT *Young's-modulus*-derived (its own provenance note says so). Archived PLA Murnaghan K is 4.46–5.39 GPa (PLA1/2/3/4 `bulk_modulus_murnaghan.json:5`), so grading PLA against it manufactures a FAIL-high. Flagging it in `assumptions[]` is NOT enough — set `decided_params.exp_K_GPa: null` (see [[plan-prohibitions-must-be-machine-effective]]); the DB path still outranks it, so a real PLA band from exp-lookup is unaffected.
- PEST carries NO `experimental_density_gcm3` at all, so `gen_prompt._exp_density_range` falls back to `density_initial/0.55` = 1.145 → band [0.974, 1.317], wrong-centered on a BINDING gate. Pin `decided_params.experimental_density_gcm3 = 1.248` (amorphous basis used by all four archived replicates; crystalline PLLA ~1.290 excluded). Archived 300 K plateau is 1.2197 g/cm3, ~2% low, PASS.
- Finite size at the class default dp=50/nchain=10: archived `mean_Rg_A = 16.691` over 10 chains, cell mass 36031.5 g/mol → L = 36.6 Å at 1.2197 g/cm3 ⇒ L/2cutoff 1.93, **L/2Rg 1.10**, L/Ree 1.03. Passing but thin. Grounding's PLAFF3 cell (dp=500/nchain=3) forecasts L/2Rg = 0.50 — decline it; Rg grows as √dp while L only grows as (nchain·dp)^(1/3).
- Exp Tg pin = 331 K (PLA member). `gen_prompt` resolves the dict by run-name prefix (`"PLA1".startswith("PLA")`), and every `experimental_tg_K` read site is `isinstance`-guarded (`gen_prompt.py:244, 259, 407-420`), so a scalar override in `decided_params` is safe as well as clearer.
- Both Murnaghan pressure ladder (`[-1000,0,1500,3000,5000]`, compression-biased) and the rate ladder `[40,80,100]` are evidence-backed in-repo — keep them. Grounding's six-rate PLAFF3 ladder fails the steps floor at 120/300/600 K/ns (166,667 / 66,667 / 33,333 < 200,000) and its feasible remainder is the retired slow-rate regime.

See [[grounding-vs-rules-conflicts]], [[planner-scope-denials]], [[pktn-reasoned-plan]].
