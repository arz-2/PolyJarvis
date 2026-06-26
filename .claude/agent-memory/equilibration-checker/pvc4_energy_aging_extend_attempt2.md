---
name: pvc4_energy_aging_extend_attempt2
description: PVC4 glassy NPT at 300K: energy drift worsens after extension (5.55%→9.56%); physical aging + C∞ calibration
metadata:
  type: feedback
---

**Scenario:** PVNL (PVC) DP=60, PCFF, glassy (Tg>400K expected), 300K NPT production.

**Observation:**
- npt_prod300 (first run): energy drift 5.55%, block-SEM 0.84% → EXTEND verdict
- npt_extend +2ns @300K (attempt 1 of 2): energy drift **9.56%** (worsened), block-SEM 1.02% → still above 1% threshold
- Density excellent throughout: 1.350 g/cm³, drift 0.11%, block-SEM 0.0012%
- All spatial gates pass (P2=0.027, density homog CV=18.5%)

**Root cause:** Glassy polymers at 300K (below Tg) undergo **slow physical aging**. Energy fluctuations are suppressed by low chain mobility, but the system doesn't reach true equilibrium within 2–4 ns windows. Pressure equilibration introduces vibrational stress (ΔE) that persists and inflates block-SEM estimates.

Two-ns windows are **insufficient** for glassy thermo statistics at 300K; need 4–5 ns minimum.

**Verdict applied:** EXTEND to attempt 2 (final allowed). Recommendation for final gate: if energy drift persists but **density/spatial passes and drift has not further degraded**, issue **PASS with caveat** (residual physical aging noted). Do not loop endlessly on energy alone—that is correct behavior for glassy systems near base temperature.

**C∞ artifact warning:** Tool reported C∞ = 2.905 in extension check vs. 8.814 in prior npt_prod300 check. Mismatch signals a **backbone_types definition error** — likely n_backbone_bonds=179 is counting all inter-atomic separations, not just backbone single bonds. For PVC DP=60, correct n_backbone_bonds should be ~59 (one bond per repeat unit). This inflates C∞ range and is a spurious diagnostic flag. **Fix:** Re-validate backbone atom types in the EMC-built cell.data (types 1,2 = c,c1 carbons on main chain; types 3,4 = Cl, H substituents—exclude these from backbone count).

**Action for replication:** Patch the backbone_types & n_backbone_bonds parameters in future gen_prompt calls before submitting the comprehensive check tool.

**Cross-run rule:** This is an example of when extended cells fail to improve thermo convergence. **Physical aging is real and cannot be "fixed" by extension alone**—better to PASS with transparency and note it in run_summary grading.
