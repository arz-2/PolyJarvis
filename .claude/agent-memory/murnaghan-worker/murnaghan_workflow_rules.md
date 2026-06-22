---
name: murnaghan_workflow_rules
description: Murnaghan pressure-series rules for glassy vs rubbery polymers, pressure defaults, and workflow assumptions
metadata:
  type: feedback
---

## Glassy vs Rubbery Routing (guides/MURNAGHAN.md Rule B)

**Rule B:** If `is_glassy=True` (Tg > 300 K):
- Use **glassy cell** at 300 K: `npt_prod300_out.data` (not rubbery `npt_production_out.data`)
- Use **symmetric ±1000 atm pressure range** by default: `[-1000, -500, 0, 500, 1000]`
- Murnaghan is the **primary glassy method** (Born was removed 2026-06-21)

If `is_glassy=False` (rubbery, Tg ≤ 300 K):
- Use **rubbery cell** at workflow temperature: `npt_production_out.data`
- Use **positive pressure range**: e.g. `[1, 100, 300, 600, 1000]` atm (old default for soft melts)

**Why:** Glassy polymers need tensile (negative) pressures to probe the stiff modulus; rubbery polymers probe only the compressive side. Pressure asymmetry is deliberate.

**How to apply:** Before calling `run_bulk_modulus_series`:
1. If task params carry `is_glassy=True`, confirm `bm_pressures_atm` is symmetric (includes negatives).
2. Route to correct equil data file:
   - glassy: `/data/<run>/lammps/npt_prod300/npt_prod300_out.data`
   - rubbery: `/data/<run>/lammps/npt_production/npt_production_out.data` (or driver-selected)

**Status:** Confirmed PSU1 2026-06-21; applies to all glassy Murnaghan submissions.

---

## Pressure Series Defaults

**Glassy (is_glassy=True):**
- `[-1000, -500, 0, 500, 1000]` atm (symmetric ±1k, guide-default)
- Temperature: 300 K (always — glassy cell)
- npt_steps: 500000 (0.5 ns/point)
- 5 stages total

**Rubbery (is_glassy=False):**
- `[1, 100, 300, 600, 1000]` atm (positive only, old soft-melt default)
- Temperature: workflow-dependent (typically 600 K melt, but may be Tg-survey point)
- npt_steps: 500000 (0.5 ns/point)
- 5 stages total

---

## Tool Parameter Notes

- `run_bulk_modulus_series` signature includes FF flags (`use_pcff`, `use_opls`, `use_trappe`) but NOT an `engine` parameter.
- Cannot explicitly request kokkos; tool defaults to `-sf gpu` (CUDA package).
- Glassy runs typically request `gpu_ids="0"` (single GPU) and `mpi=1`.

---

## Memory Links

- [[murnaghan_submission_issues]] — known blocker bugs (log-path, missing kokkos support)
- [[project_born_method_impl]] — Born method (removed from glassy path 2026-06-21; context)
