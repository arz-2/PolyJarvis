---
name: paywalled-cte-numeric-values
description: WebFetch cannot get past ACS/Elsevier/Springer paywalls for exact numeric alpha_glass/alpha_melt values; qualitative claims from search snippets are the practical ceiling
metadata:
  type: feedback
---

For `cte_glass_melt` grounding on cis-PBD1, two verified MD papers (Shamsieva2023,
10.1007/s00894-023-05658-6; Krushev&Paul2002, 10.1016/S0032-3861(01)00628-0) both explicitly report
glassy-vs-melt thermal expansion coefficients for the exact target microstructure, but WebFetch hit
403s on pubs.acs.org, sciencedirect.com, and (via redirect) springer's authorize wall every time —
only PubMed's own summary page and WebSearch snippets were fetchable.

**Why:** the schema wants a numeric `alpha_glass_per_K`/`alpha_melt_per_K`, but abstract-only access
never carries that figure/table data — it's always in the full-text figures.

**How to apply:** for CTE (and likely other numeric-table-only claims), budget for landing on
`confidence: "low"` with `alpha_*_per_K: null` plus a qualitative claim, rather than spending
multiple WebFetch retries chasing a paywalled numeric value. Try PubMed's own page and Google
Scholar cache before ResearchGate/publisher pages — ResearchGate is reliably 403 in this
environment.

Update (PLA1, 2026-08-14): for JCTC/ACS articles, try the NCBI PMC mirror
(`pmc.ncbi.nlm.nih.gov/articles/PMC<id>`) before giving up — it fetched clean full text (incl.
exact numeric density/Tg/CTE targets and cooling-rate list) for a paper whose `pubs.acs.org` DOI
redirect 403'd. `ncbi.nlm.nih.gov/pmc/articles/...` itself just 301-redirects to the `pmc.ncbi.nlm.nih.gov`
host — fetch that directly to save a round trip. sciencedirect.com and a second pubs.acs.org
article both still 403'd with no PMC mirror available, so this is a partial workaround, not a
general fix.
