---
name: project_panh_class_defaults_audit_2026-08-26
description: PANH (polyanhydride) dp_typical/dp_min/nchain class-default re-audit -- no MD source found either way
metadata:
  type: project
---

Audited PANH class defaults (dp_typical=40, dp_min=20, nchain=10) against MD literature for
poly(sebacic anhydride) / polyanhydrides generally on 2026-08-26. Result: **no verified MD
convergence source found at all** -- not confirming, not contradicting. Multiple targeted
searches (polymer name + DP/chain-length, glass-transition amorphous-cell, PCFF force field,
entanglement-MW/packing-length) all came up empty for polyanhydride-specific MD before the
session's web-search budget ran out. Only hit: a 2014 experimental synthesis/GPC paper
(10.1007/s10965-014-0426-3), correctly excluded as out-of-scope (no MD component).

Evidence-store query returned only two `similar_class` PEST/PET hits at 0.67 similarity, both
already flagged non-binding for their own class in [[project_pest_class_defaults_audit_2026-08-26]]
(no DP sweep in either) -- did not transfer them onto PANH.

**Why:** confirms polymer_rules.json's own existing self-flagged note ("polyanhydride-specific
PCFF MD literature is sparse... genuine, confirmed-open validation gap") is still accurate as of
this date -- this class remains a real open gap, not just an unexplored one.

**How to apply:** if re-auditing PANH again, don't re-run the same broad searches --
they're documented dead ends here. If the web-search budget allows deeper search next time, try
narrower angles not yet tried: specific catalyst/DP GPC papers cross-referenced against any
follow-up MD paper by the same authors, or "poly(butylene succinate)"/aliphatic-polyester MD
DP-convergence studies as a closer structural analogy than PET (PANH backbone is aliphatic
diacid-derived, PET is aromatic).
