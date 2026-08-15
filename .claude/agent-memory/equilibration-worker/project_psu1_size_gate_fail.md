---
name: project-psu1-size-gate-fail
description: PSU1 (PSFO/PCFF) inspect_data_file size gate failed at nchain=20, needs rebuild at nchain=24
metadata:
  type: project
---

PSU1 melt-phase submission attempt 1 blocked at the size gate: `inspect_data_file` with
`lj_cutoff=9.5`, `target_density_gcm3=1.24`, `nchain=20` on
`/home/arz2/PolyJarvis/data/PSU1/lammps/equil/cell.data` (n_atoms=27040, as-built box 84.0 A)
returned `SIZE_CHAIN_SELF_IMAGE`: predicted compressed L=66.67 A vs 2*Rg=70.5 A (L/2Rg=0.946).
`finite_size_forecast.remedy` = nchain x1.18, nchain_suggested=24. Chain was NOT submitted.

**Why:** Same pattern as [[project_peek1_equil_chain]] (PKTN, nchain 8→17) — packed Rg for this
class/chain-length combination is large relative to the target-density box edge; EMC cell must
be rebuilt with more chains before equilibration, not fixed by running longer.

**How to apply:** When orchestrator resubmits PSU1 with a rebuilt cell at nchain>=24, re-run
inspect_data_file first to confirm the forecast now passes before generating/submitting the
workflow.
