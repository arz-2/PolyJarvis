---
name: psfo-rules-audit-gap-reconfirmed
description: PSFO (polysulfone/PSU/PES/PPSU) rules-audit (2026-08-26) reconfirmed the PCFF-vs-experiment MD validation gap is genuine; two tangential Class-II-family sightings found, neither with a signed error
metadata:
  type: project
---

Re-audited PSFO class defaults (forcefield=PCFF, electrostatics=pppm, tg_rates=[25,50,100],
exp Tg PSU=463K, exp density PSF=1.24-1.25 g/cm3, exp K_T=4.0-5.5 GPa, alpha_glass/melt from
Mark2007 Tait fits) against the persistent evidence store plus a fresh 2026-08-26 search.

Store query found only an exact_class PPESK hit (10.1016/j.commatsci.2018.05.039 -- COMPASS on
5 novel, unsynthesized poly(phthalazinone ether sulfone ketone) variants, no experimental
comparator since the polymers are novel designs) and two `similar_class` PKTN/PCBN hits that
are about PEEK/BPA-PC, not polysulfone -- correctly excluded from PSFO's own density/Tg targets
per this worker's own rule against importing another class's validation numbers.

Fresh search (WebSearch budget exhausted this session -> fell back to Crossref/Semantic Scholar
API) surfaced one new preprint: a 2021 Research Square paper (10.21203/rs.3.rs-1109742/v1) on
COMPASS-force-field MD of PSU/PSMA polymer blends, comparing miscibility predictions against a
DSC-observed Tg shift. Full text 403'd; only the API abstract was recoverable, and it reports no
pure-PSU density or Tg number -- family-usage color only, changes no recommendation.

**Why:** confirms the class's own `ff_note` admission ("no PCFF- or compass-vs-experiment
density/tg number for polysulfone... has been located") is not stale -- a second, independent
pass (store query + fresh search) still turns up zero signed-error numbers, only two Class-II-
family sightings on adjacent/blend chemistry.

**How to apply:** if PSFO comes up again for grounding, don't expect a fresh search to surface a
genuine vs-experiment PSU density/Tg number without a new paper being published -- the PPESK
2018 and PSU/PSMA-blend 2021 preprint are very likely the best on-family MD hits available. Same
pattern as [[psul_pps_rules_audit_gap_confirmed]] and [[pura_rules_audit_gap_reconfirmed]]: some
classes' literature gaps are real and durable, not search-effort artifacts. Note also the
WebSearch-budget-exhaustion environmental block recurred here exactly as in
[[pphs_rules_audit_gap_reconfirmed]] -- Crossref/Semantic Scholar API fetches via WebFetch are a
usable fallback path when WebSearch itself is unavailable mid-session.
