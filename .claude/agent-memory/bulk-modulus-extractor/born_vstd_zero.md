---
name: born-vstd-zero
description: V_std=0 in Born+NVT log diagnostics is expected (NVT = fixed volume); not an artefact
metadata:
  type: project
---

In the Born+NVT method the simulation is NVT (constant N, V, T). Volume is exactly fixed, so V_std_A3=0 is correct and not a sign of a broken log parse. The Born tool uses P variance (Var_P_atm2) for the fluctuation correction, not V variance.

**Why:** Reminder to not misread the diagnostic as a parse failure when V_std=0 appears.

**How to apply:** If bulk_modulus_born.json shows V_std_A3=0, do not flag as a data issue.

[[born-sem-inflation]]
