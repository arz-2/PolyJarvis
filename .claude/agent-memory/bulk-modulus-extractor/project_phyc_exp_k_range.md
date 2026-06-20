---
name: project_phyc_exp_k_range
description: exp_K_range=[0.3,0.8] GPa in polymer_rules for PHYC appears too low; PE1 Murnaghan B0=1.46 GPa
ingested_at: 2026-06-20
metadata:
  type: project
---

The `exp_K_range` for PHYC in `polymer_rules.json` is set to [0.3, 0.8] GPa. PE1 (polyethylene, TraPPE-UA) yielded B0=1.46 GPa (Murnaghan) and B_dyn=1.59 GPa (fluctuation). Literature values for PE bulk modulus are ~1.5–2.0 GPa for the amorphous melt/rubbery state at ambient pressure, so the simulation result is physically reasonable.

**Why:** The range [0.3, 0.8] GPa may conflate shear modulus (which is very low for rubbers, ~0.001 GPa) with bulk modulus (which is ~1–3 GPa even for compliant polymers). Rubbers are nearly incompressible — bulk modulus is not small.

**How to apply:** When reporting PE or PHYC bulk modulus results, flag that B0 > exp_K_range upper bound but note the range likely needs correction in polymer_rules.json — do NOT massage the computed value. Report B0 truthfully and recommend the orchestrator review the exp_K_range entry.
