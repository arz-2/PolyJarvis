---
name: feedback-publisher-webfetch-403-arxiv-fallback
description: ACS/AIP/ScienceDirect/RSC/PMC/ResearchGate/Academia.edu/MDPI often 403 WebFetch; arXiv preprints are the reliable fallback for full-text verification
metadata:
  type: feedback
---

Major publisher domains (pubs.acs.org, pubs.aip.org, sciencedirect.com — including the
`/science/article/am/` author-manuscript path, pubs.rsc.org, pmc.ncbi.nlm.nih.gov,
researchgate.net, academia.edu, mdpi.com) frequently return HTTP 403 to WebFetch, even via a
doi.org redirect that itself resolves fine. This is not occasional — in one PSTR grounding session
essentially every publisher fetch attempt across 7+ distinct domains failed this way, while every
arxiv.org/abs/ or arxiv.org/html/ fetch succeeded and returned real, specific content (numbers,
quotes) that could back a `verified: true` source.

**Why:** Publisher sites apparently block or challenge the WebFetch tool's request pattern
(possibly bot/rate-limit detection); arXiv does not.

**How to apply:** When a target claim is behind a blocked-prone publisher domain and a DOI-redirect
WebFetch 403s, don't burn many retries across mirrors (researchgate/academia.edu/PMC also tend to
403 the same content) — instead (a) search specifically for an arXiv preprint or MDPI/open-access
alternative covering the same finding, since recent (2025-2026) MD/ML-force-field benchmarking
papers often restate a target polymer's cited experimental density/Tg validation number even when
their own method is an ML force field (this still satisfies the "experimental density/Tg an MD
study cites as its own validation target" brief), and (b) if no arXiv-hosted equivalent exists for
a specific numeric claim (e.g. exact %-density-deficit tables), don't fabricate `verified: true` —
report the DOI as existing/topically-matched but the claim as unconfirmed full-text, and let
`confidence` fall accordingly rather than overclaiming from a title/search-snippet match alone.
