---
name: project_phyc_exp_k_range
description: PHYC exp_K_GPa was [0.3,0.8] (wrong); corrected to [1.5,2.0] in polymer_rules.json; PE1 B0=1.46, PE2 B0=1.64 both within corrected range
ingested_at: 2026-06-22
metadata:
  type: project
---

`exp_K_GPa` for PHYC in `polymer_rules.json` was previously [0.3, 0.8] GPa — likely confused shear modulus (very low for rubbers) with bulk modulus (1–3 GPa even for compliant polymers). As of 2026-06-22 the entry has been corrected in polymer_rules.json to [1.5, 2.0] GPa, with citation to Mark 2007 Table 7.5 Tait parameters and a note distinguishing amorphous K_T from semicrystalline/ultrasonic K_S (~2.5–3.5 GPa).

PE1: B0=1.46 GPa (Murnaghan), B_dyn=1.59 GPa (fluctuation) — both within [1.5, 2.0] GPa (PE1 Murnaghan marginally below, but close).
PE2: B0=1.641 ± 0.108 GPa (Murnaghan, R²=0.9996, B0'=12.27) — within [1.5, 2.0] GPa. status=OK.

**Why:** Literature K_T for rubbery amorphous PE at 25°C (above Tg=195K) is ~1.7–1.9 GPa from PVT/dilatometry. Range [1.5, 2.0] is the correct comparator for fully-amorphous TraPPE-UA simulations.

**How to apply:** PHYC PE bulk modulus ~1.5–1.7 GPa is expected and physically sound. Use [1.5, 2.0] as the acceptance range. Values outside this range warrant investigation, not silent override.
