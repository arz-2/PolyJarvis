---
name: panh-literature-absent
description: Polyanhydride (PANH) class, incl. poly(sebacic anhydride), has essentially no dedicated MD simulation literature
metadata:
  type: project
---

Ran a full literature-grounding pass for poly(sebacic anhydride) (PANH, confidence=low)
on 2026-08-05. ~10 targeted WebSearch queries across forcefield, electrostatics, system
size/DP convergence, cooling rate, and density/Tg validation targets — all MD-simulation
scoped — turned up zero polyanhydride-specific or poly(sebacic anhydride)-specific MD
studies. Only tangential hits: a broad 315-polymer OPLS3e high-throughput screen (Afzal
2021, see [[panh-ff-citation-mismatch]]) with no polyanhydride coverage, and a PEO/PEG
polymer-electrolyte MD-Tg-methodology review (Klajmon-adjacent, doi
10.1021/acs.jpcb.4c06018) giving only generic cooling-rate context (5-5000 K/ns range
across unrelated polymers).

**Why:** Polyanhydrides are a niche, hydrolytically-labile biomedical polymer class;
mainstream MD force-field literature does not appear to have engaged with them the way it
has for PLA/PEG/PVP/PEEK/PC etc. This matches (and is independently confirmed by) the
existing polymer_rules.json PANH entry's own warning note: "polyanhydride-specific PCFF
MD literature is sparse."

**How to apply:** Don't spend excessive search budget trying to force polyanhydride-
specific literature on future PANH runs (poly(sebacic anhydride), CPPA, PSAD, PLGA-like
anhydrides) — a handful of well-chosen searches confirming absence is sufficient; write
an honest all-fields-low-confidence grounding JSON and let the planner fall back to
polymer_rules.json defaults rather than iterating further. If a future run finds genuine
polyanhydride MD literature, this memory should be updated/removed.
