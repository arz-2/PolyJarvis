---
name: feedback_trappe_ua_validation
description: EMC TraPPE-UA .data files have no Coeffs sections; validate_data_file flags 4 blocking errors that are false-positives — coefficients are in the params file
metadata:
  type: feedback
ingested_at: 2026-06-05
---

EMC-built TraPPE-UA `.data` files (PHYC, PDIE, PSTR classes) contain topology only — no Pair/Bond/Angle/Dihedral Coeffs sections. `validate_data_file` will always return `valid: false` with 4 blocking errors about missing Coeffs sections. This is a **known false-positive**, not a real blocker.

**Why:** EMC separates topology (`.data`) from force field parameters (`emc_build.params`). The coefficients are loaded via `include emc_build.params` in each LAMMPS script. The generator wires this automatically when `params_file` is supplied.

**How to apply:** Before escalating on a `valid: false` result for an EMC TraPPE-UA system, always read `emc_build.params` and confirm it contains the expected Pair/Bond/Angle/Dihedral Coeffs (count must match header type counts). If it does, proceed — the validation error is a false-positive. If the params file is empty or missing coeffs, that is a genuine Stage 1 failure. Also confirm `net_charge_e = 0.0` (TraPPE-UA hydrocarbons carry no partial charges). See also [[feedback_chain_no_data_file]].
