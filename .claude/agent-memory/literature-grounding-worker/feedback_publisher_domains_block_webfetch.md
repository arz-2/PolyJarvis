---
name: publisher-domains-block-webfetch
description: Which publisher domains 403 the WebFetch tool vs which work, and the PDF-binary-fallback trick
metadata:
  type: feedback
---

WebFetch returns HTTP 403 (bot-blocked) on ACS (pubs.acs.org), RSC (pubs.rsc.org),
MDPI (mdpi.com), and ResearchGate for essentially every article URL, including DOI
redirects to those hosts — retrying the same domain a second or third time does not
help, stop after one attempt per domain and route around it instead.

What reliably works instead:
- arXiv abstract pages (`arxiv.org/abs/...`) fetch fine and WebFetch can summarize them.
- arXiv PDF fetches (`arxiv.org/pdf/...`) often fail to *parse* as text via WebFetch,
  but the tool still saves the raw PDF binary to a local tool-results path (reported
  in the WebFetch output). Use the `Read` tool directly on that saved PDF path (with
  a `pages` range) — this works and gives full figure/table/text access that WebFetch's
  own summary missed.
- PubMed/PMC (`pubmed.ncbi.nlm.nih.gov`, `pmc.ncbi.nlm.nih.gov`) has fetched successfully
  where publisher-direct hosts 403'd.

**Why:** discovered while grounding PE (PHYC) system-size decision — 7 consecutive 403s
across ACS/RSC/MDPI/ResearchGate before switching to the arXiv-PDF-then-Read approach,
which successfully retrieved Hoy/Foteinopoulou/Kröger (Phys. Rev. E 80, 031803, 2009)
in full.

**How to apply:** when a search turns up a promising DOI/URL on one of the blocked
domains, immediately check whether an arXiv preprint or PMC copy exists before
re-attempting WebFetch on the publisher domain a second time. If a WebFetch PDF fetch
"fails to parse," check the tool output for a saved local file path before giving up on
that source — read it directly.
