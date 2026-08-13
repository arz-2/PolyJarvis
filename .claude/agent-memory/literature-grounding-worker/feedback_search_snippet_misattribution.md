---
name: feedback-search-snippet-misattribution
description: WebSearch's own summary text can misattribute a numeric claim to the wrong paper — always WebFetch the actual source before citing
metadata:
  type: feedback
---

On the PEEK1 grounding run, WebSearch's synthesized answer twice stated that Suter et al. 2025
(J. Chem. Theory Comput., 10.1021/acs.jctc.4c01364, PMC11823416) reports a PEEK-specific
"+112.2 K rate-inflated Tg overestimate." WebFetch of the actual PMC full text showed the paper
studies six cross-linked epoxy resins only (DGEBA/DGEBF/TGPAP x 44DDS/MDEA) and never mentions
PEEK — the "+112.2 K PEEK" figure almost certainly leaked in from a different, self-referential
arxiv hit (a "PolyJarvis" paper describing this very project) that also kept surfacing in the same
searches.

**Why:** the agent doc's "verify every source before citing" rule exists precisely for this
failure mode — a plausible, specific-sounding numeric claim from a search-engine summary is not
evidence the source paper actually contains it. Had I trusted the snippet, I would have grounded
PEEK's cooling-rate/Tg-overestimate field on a source that doesn't support it at all.

**How to apply:** any time a WebSearch synthesized answer attributes a specific number to a named
paper, WebFetch that paper directly (PMC/DOI, not the search snippet) before writing it into the
grounding JSON — especially when the same search also surfaces a self-referential PolyJarvis
paper, which should never be treated as an independent literature source.
