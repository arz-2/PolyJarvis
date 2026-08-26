---
name: pstr-rules-audit-ps-ff-density-tg-corroboration
description: PSTR/PS 2026-08-26 rules-audit findings — PCFF/pppm/1.05 g cm-3/373K defaults corroborated by fresh 2025-2026 preprints; COMPASS-switch question stays open
metadata:
  type: project
---

2026-08-26 PSTR (polystyrene, `*CC(*)c1ccccc1`) class-default re-audit of
`guides/polymer_rules.json`, output at
`data/PSTR_rules_audit/raw/literature_grounding_ff_protocol.json`.

**Result: agreement, no change recommended.** polymer_rules.json's PSTR defaults
(forcefield=PCFF, electrostatics=pppm, experimental_density_gcm3.PS=1.05 @300K,
experimental_tg_K.PS=373) are corroborated by fresh 2025-2026 arXiv preprints:
- arXiv:2601.17137 (Srivastava et al. 2026 — matches the `Srivastava2026` citation the class
  already lists) confirms PS exp density 1.05 g/cm3 @300K and shows PCFF beats GAFF2 on Tg-RMSE
  across a 12-polymer benchmark including PS (76.77K vs 119.74K, aggregate not PS-specific).
- arXiv:2510.13696 (SimPoly) confirms PS exp Tg 373K as the paper's own MD-validation target.

**Why:** polymer_rules.json's own citation trail (`citations: [Srivastava2026, Tang2022,
Soldera2006, NkepsuMbitou2025, Klajmon2023]`) turned out to be independently reproducible by fresh
search — the class's grounding is not stale.

**Open item not resolved this session:** polymer_rules.json's own `ff_note` already documents a
PCFF aromatic-ring density deficit (-5.85% to -6.32% measured on PS internally) and cites
jp980939v (Sun 1998, COMPASS founding paper) for a benzene/toluene -6.3%/-6.5% deficit that
COMPASS reduces to -1.1%/-1.2%; `field_override='compass'` is noted as EMC-admissible but
build-untested against PS's SMILES. I could not independently re-verify the exact jp980939v
percentages this session (ACS blocks WebFetch — see [[feedback_publisher_webfetch_403_arxiv_fallback]]),
so this remains exactly as documented, neither strengthened nor weakened. A future PSTR audit with
better publisher access should try to close this specific gap.

**How to apply:** Treat PSTR's current defaults as re-confirmed as of 2026-08-26; don't re-litigate
forcefield/density/Tg without new evidence. The COMPASS-override question is the one still-live
thread worth another look if journal access improves.
