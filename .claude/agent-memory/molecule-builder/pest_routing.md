---
name: pest-routing
description: PEST (polyester, e.g. PLA/PET/PCL) routes to EMC/PCFF, charge none, pppm electrostatics, use_pcff:true
metadata:
  type: reference
---

PEST (class 9, Polyester — PLA, PET, PCL) routing for Stage 1 build:

- preferred_builder: emc, preferred_ff: pcff, ff_confidence: high
- classify_polymer returns no co_occurring_groups and no warning for a clean PLA repeat unit (`*C(C)C(=O)O*`).
- EMC field auto-selected as pcff from polymer_class — do NOT pass a field argument.
- RESULT fields: ff: pcff, charge_method: none, electrostatics: pppm, lammps_flags {"use_pcff": true, "use_opls": false}.
- PCFF has explicit ester types (c_1, o_2, oe); Klajmon2023 (10.1021/acsapm.0c00524) benchmarks PLA/PEG with AA-MD.

Parallel to [[psfo-routing]] — both EMC/PCFF, charge none, pppm.
