---
name: feedback-chain-pcff-params-file
description: For EMC PCFF builds, pass params_file (not omit data_file) to run_lammps_chain to suppress Coeffs false-positive while retaining preflight validation
metadata:
  type: feedback
ingested_at: 2026-06-10
---

For EMC PCFF builds, Coeffs sections live in the `.params` file, not the `.data` file. The correct approach is:
- Pass `params_file=` to both `generate_equilibration_workflow` and `run_lammps_chain`
- Keep `data_file=` in `run_lammps_chain` only if you also pass `params_file=` (suppresses the Coeffs false-positive)
- Omitting `data_file` entirely from `run_lammps_chain` also works (prior approach) but loses preflight validation

**Why:** Original memory note said "omit data_file for EMC builds" — this was overly broad. With `params_file` passed, pre-flight knows Coeffs are elsewhere and does not block. Confirmed for PAMD/Nylon1 run (2026-06-06).

**How to apply:** For all EMC PCFF classes (PCBN, PAMD, PKTN, PSFO, PIMD, POXI, PEST, PSUL, PURT, PANH, PPHS, PACR, PIMN, PVNL, PPNL): always pass `params_file` to both generate and run calls. Can safely include `data_file` in run_lammps_chain when params_file is also present.

[[feedback_trappe_ua_validation]]
