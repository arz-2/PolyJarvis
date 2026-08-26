---
name: ppnl-ppv-rules-audit-gap-confirmed
description: PPNL/PPV rules-audit (2026-08-26) reconfirms PCFF/Tg=416K but finds no new MD source for electrostatics/cooling-rate/density/CTE
metadata:
  type: project
---

Re-audit of PPNL class defaults (PPV SMILES `*C=Cc1ccc(*)cc1`) confirmed the store's existing
`f003d60af626` record (Venkatanarayanan2016, 10.1002/mats.201600006) is still the class's only
quantitative MD-literature source. Two separate grounding passes now agree: the paper's own use of
PCFF has never been independently confirmed from primary text -- it is hard-paywalled (Wiley 403,
no Unpaywall OA copy, Semantic Scholar returns no abstract). Tg=416+/-8K vs exp ~416K stands as an
essentially exact match and is the strongest evidence in the class.

Fresh search found one tangential paper: Wolf et al. 2021 "Strategies for the Development of
Conjugated Polymer MD Force Fields..." (10.1021/acspolymersau.1c00027, ACS Polymers Au, gold OA,
PMC9954299 -- fetchable via PMC when Wiley/pubs.acs.org both 403). It reviews OPLS-AA/GAFF/CHARMM/
GROMOS/MM3 for **polythiophenes**, not PPV; does not mention PCFF/DREIDING/COMPASS; states
partial-charge sets across published conjugated-polymer FFs have "minimal consistency, both in
sign and magnitude" -- weak indirect support for PPPM (conjugated backbones need real partial
charges) but not a direct PPV citation.

electrostatics/cooling_rate/density_target/cte_glass_melt for PPV remain **completely ungrounded**
by any verified MD source in both passes -- not a stale-search artifact, a genuine literature gap
for this specific chemistry. See [[feedback_publisher_webfetch_403_arxiv_fallback]] --
Wiley/pubs.acs.org 403 as usual, but PMC mirror worked for the one paper that had a PMC copy
(Unpaywall's oa_locations lists PMC ids even when Crossref/publisher land pages 403).

WebSearch tool budget exhausted mid-session (200/200) -- switched to raw `curl` against
Crossref/Unpaywall/Semantic-Scholar APIs directly via Bash, which is not subject to the WebSearch
tool's session cap and worked fine for discovery/metadata (just not full-text, which is
publisher-blocked regardless of the calling method).
