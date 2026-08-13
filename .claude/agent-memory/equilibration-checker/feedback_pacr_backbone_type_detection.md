---
name: pacr_backbone_auto_detection_includes_carbonyl
description: PMMA/PACR: backbone_types=[1] intended, but check_equilibration_comprehensive auto-expanded to [1,3]; type 3 is carbonyl (c_1), not backbone — verify C(t) metrics if issue occurs
metadata:
  type: feedback
  ingested_at: 2026-08-11
---

**Issue:**
For PMMA1 (PACR, DP=50), I derived backbone_types=[1] ("c" = aliphatic carbons only) based on the .data file atom type names and bond connectivity. The carbonyl carbon (type 3, "c_1") should NOT be included.

However, when calling `check_equilibration_comprehensive` with backbone_types=[1], the result JSON shows backbone_types=[1, 3].

**Why:**
The tool may have an auto-detection feature that expands backbone_types to include nearby heavy atoms. For PMMA/PACR:
- Type 1: aliphatic carbons (backbone + methyl/methoxy side groups)
- Type 3: carbonyl carbons (NOT backbone — sp² conjugated to ester group)

**Impact:**
- C(t) autocorrelation computed on mixed backbone + carbonyl atoms
- tau_relax is large/unrealistic anyway (3% decay only) so severity unclear
- End-to-end distance (R_ee) likely still valid as it uses chain topology

**How to apply:**
If PACR runs show anomalous C(t) behavior, check whether the tool auto-added type 3 to backbone_types, and if so, flag as a potential root cause. May want to dig into the comprehensive check tool's backbone detection logic.

For now, rely on density/homogeneity/P2 gates which are unambiguous.
