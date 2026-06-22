---
name: born-stage-retired
description: born mechanical stage removed pipeline-wide 2026-06-21 (PCFF+PPPM virial incompatibility); glassy K path is now Murnaghan NPT
metadata:
  type: project
---

The `born` planned_stage was REMOVED from the PolyJarvis pipeline on 2026-06-21. `gen_prompt.py --stage born` now hard-errors.

**Why:** PCFF+PPPM virial incompatibility caused 3/3 born NVT-matrix runs to fail (see guides/BORN_MATRIX.md). Born was previously the preferred glassy K_T path (NVT Born matrix).

**How to apply:** For any **glassy** polymer (is_glassy=TRUE) requesting bulk_modulus, the mechanical track's first stage must be `murnaghan` (NPT compression at 300 K on npt_prod300_out.data), NOT `born`. Per guides/MURNAGHAN.md Rule A/B:
- bm_method = "murnaghan", bm_pressures_atm = [-1000,-500,0,500,1000] (+-1000 atm symmetric), is_glassy_hint = true in decided_params.
- murnaghan success_criteria: fit_converged=true, eos_r_squared_min ~0.999, B0_prime in [4,20], volume_equilibrated at all points.
- `deform`-worker (3-direction uniaxial) remains the documented fallback if Murnaghan fails.
- Widen to +-2000 atm for very stiff (K>8 GPa, e.g. PEEK) if fit doesn't converge at +-1000.

When revising a deterministic high-confidence plan for this, keep class confidence=high but log the swap in critique.findings and provenance.revised_* (this is a pipeline change, not a class re-reasoning). Related: [[pktn_rigid_backbone_screening]].
