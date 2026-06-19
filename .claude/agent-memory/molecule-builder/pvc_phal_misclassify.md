---
name: pvc-phal-misclassify
description: classify_polymer returns PHAL (OPLS-AA) for PVC *CC(Cl)*; correct route is PVNL/PCFF
metadata:
  type: feedback
---

`classify_polymer("*CC(Cl)*")` (PVC) returns **PHAL** (class 5, OPLS-AA,
ff_confidence=high) because it flags the C–Cl bond as halogenated. This is a
**false flag for the FF route** — PVC is a vinyl-backbone polymer and the
project deliberately routes it to **PVNL → PCFF**.

**Why:** PHAL examples are fluorinated (PTFE/PVDF/PCTFE). PVC is listed
explicitly as a PVNL example in `guides/polymer_rules.json`, and PCFF has the
C–Cl increments (build-tested PASS, 3620 atoms for dp=60/nchain=10). PCFF gives
better thermomechanical accuracy here than OPLS-AA.

**How to apply:** `classify_polymer` is a Rule-0 logging/sanity step, NOT an FF
override mechanism. When the task prompt / approved plan specifies
`polymer_class: PVNL`, build with PVNL even if the classifier says PHAL. Log the
divergence in D-01. Same pattern as the PSTR override (project intentionally
overrides a naive class default for FF accuracy). Submit EMC with PVNL → field
auto-selects pcff, lammps_flags use_pcff:true. See [[emc-output-naming]].
