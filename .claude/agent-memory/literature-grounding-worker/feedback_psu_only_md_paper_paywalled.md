---
name: psu-only-md-paper-paywalled
description: The single PSU-specific (bisphenol-A polysulfone) MD literature hit is fully paywalled with no accessible abstract anywhere
metadata:
  type: feedback
---

For PSU/Udel (PSFO class), the only PSU-specific MD simulation paper findable is Fan & Hsu,
Macromolecules 1992, 25, 266-270 (DOI 10.1021/ma00027a044, "Application of the Molecular
Simulation Technique to Characterize the Structure and Properties of an Aromatic Polysulfone
System. 2. Mechanical and Thermal Properties"). The DOI resolves and CrossRef bibliographic
search confirms title/journal/year, but ACS full text returns 403, and no abstract text is
recoverable via ResearchGate, Semantic Scholar, or Google search snippets either (all blocked or
empty) — unlike some paywalled papers where a WebSearch snippet at least surfaces the abstract.

**Why:** [[feedback_paywalled_cte_numeric_values]] already covers the general paywall problem;
this is the sharper case where a source is class-specific and directly on-topic but literally zero
numeric content is extractable, so it can only ever back a weak "such a paper exists" claim
(verified:true for DOI resolution) and must NOT back specific recommendation values
(verified:false, confidence stays low/medium via other class-II general precedent instead).

**How to apply:** For PSFO/PSU runs, don't keep re-searching for this paper's numbers — accept
`verified:false` for anything density/Tg/CTE-specific attributed to it and fall back to general
PCFF-class-II precedent (Sun1994, Bejagam2020) plus handbook density/Tg ranges annotated as
"not independently literature-MD-confirmed."
