---
name: project_pmma1_equil_chain
description: PMMA1 PACR/PCFF glassy equilibration chain (2026-08-10) — melt prefix + cooldown tail, both submitted
metadata:
  type: project
---

PMMA1 run — PACR (PMMA) polymer class, PCFF force field, split melt/cooldown submission.
temp=550 K, max_temp=630 K, n_atoms=7520 (identical cell size/box to prior PMMA3 run).

Melt prefix (7 stages: minimize → nvt_softheat → npt_compress → npt_pppm → npt_cool →
nvt_production → npt_production), chain_id=2419d125, completed cleanly.
Cooldown tail (2 stages: npt_cool300 → npt_prod300), chain_id=1a503f30, submitted 2026-08-10
after gate override (see below). Both phases: engine=kokkos, gpu_ids=0, mpi=1,
velocity_seed=null (random — not pinned for this run).

The phase=melt equil-check gate initially returned STRUCTURAL_FAIL on density_homogeneity for
this run, but that was diagnosed as a **gate metric artifact**: it compares a mass-weighted CV
against a count-based Poisson floor, and the measured value was actually below a randomized-
placement control. Orchestrator/human overrode to PASS and cleared the cooldown tail for submission.

**Why:** glassy polymers >300 K use the melt/cooldown split to gate cell homogeneity before
committing to the slow 300 K cool + production stages; the homogeneity check itself can produce
false STRUCTURAL_FAIL when its statistical floor is mismatched to the CV weighting scheme.
**How to apply:** if resubmitting/extending PMMA1's cooldown phase, reuse
`_pending_cooldown_stages.json` rather than calling generate_equilibration_workflow again (already
consumed once for this run — file may need regenerating only if the melt prefix itself changes).
If another run's phase=melt gate flags density_homogeneity STRUCTURAL_FAIL, check whether it's
this same mass-weighted-CV-vs-count-floor artifact before treating it as a real packing failure —
see equilibration-checker's memory for the gate-side fix if one lands there.

**Re-anneal 2026-08-10/11:** post-cool 300K density came in −6.02% vs exp (UNDER_ANNEALED_COOLING)
— the original npt_cool300 ramp (550→300K in 1e6 steps = 250 K/ns) was too fast for the liquid
regime to track equilibrium volume. Melt itself (npt_production_out.data, chain 2419d125) was
correct (−0.4% density) — resumed from it rather than re-melting. Re-ran only npt_cool300+npt_prod300
with npt_cool300_steps doubled to 2,000,000 (125 K/ns), chain_id=83b85f08, gpu_ids=0, mpi=1,
engine=kokkos. Pattern: call generate_equilibration_workflow with the ORIGINAL args (same temp/
max_temp/params_file/velocity_seed) plus only the changed step-count override, slice
run_order.index("npt_production")+1: onward, verify the slice's npt_cool300 input_data points at
the existing npt_production_out.data (not a fresh melt), then submit just that 2-stage tail.
**Why:** cooling rate through Tg controls whether the liquid-regime volume relaxation can track
the NPT barostat; too-fast cooling freezes in excess free volume → density undershoot on glassy
polymers cooled from a high anneal temp.
**How to apply:** if npt_prod300 density is still low after this 2x slowdown, the recovery ladder's
next rung should slow npt_cool300 further (e.g. 4x baseline) rather than re-melting — the melt
itself was already validated correct.
