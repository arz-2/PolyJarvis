---
name: feedback_deform_3dir_g_negative
description: 3-dir deform: G<0 in some directions is a small-cell artifact; K_mean is still valid if cross-direction spread <20%
metadata:
  type: feedback
---

In 3-direction uniaxial deform runs on small amorphous cells (PLA2, PEST/PCFF), the y and z directions
can produce negative G (e.g., G_y=-0.60, G_z=-0.65 GPa) because C11 < C12 in those directions — a
local anisotropy artifact of the small periodic cell and random chain packing.

**Why:** The within-direction isotropy_delta_pct (C12_yy vs C12_zz disagreement) was 28-57% for PLA2,
and G < 0 for y/z directions. However, the K values across all three directions were tight (K_x=3.275,
K_y=3.421, K_z=3.553 GPa), giving cross-direction K_std/K_mean = 4.1% — well within the 20% gate.
K from (C11+2C12)/3 is more robust than G from (C11-C12)/2 because K averages positive/negative
deviations across the two transverse stresses.

**How to apply:**
- Do NOT flag G<0 as a hard failure if cross-direction K spread < 20% and all fit_r2 >= 0.90.
- Report K_mean as bulk_modulus_GPa; report G and E from x-direction only (the best-behaved one).
- Flag in notes: "G<0 for y/z directions — small cell anisotropy; K_mean robust at 4.1% spread."
- The within-direction isotropy_delta_pct from extract_bulk_modulus_deform (C12_yy vs C12_zz) is NOT
  the same as the cross-direction K spread metric used in the 3-dir guide. Check cross-direction manually.

See [[feedback_murnaghan_low_b0prime]] for PLA2 Murnaghan failure that triggered this deform fallback.
