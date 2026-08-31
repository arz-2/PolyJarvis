---
name: pphs-rules-audit-gap-reconfirmed
description: PPHS class-default rules audit (2026-08-26) — no MD study validates PCFF on any polyalkoxyphosphazene; formal ff_justification_doi actually uses DREIDING
metadata:
  type: project
---

PolyJarvis_v2 `polymer_rules.json` routes PPHS (polyphosphazenes, e.g. poly(diethoxyphosphazene)
`*N=P(*)(OCC)OCC`) to `preferred_ff="pcff"`. A 2026-08-26 rules-audit re-check found the store's
only two PPHS forcefield records both undercut PCFF support rather than confirm it:

- The class's own formal `ff_justification_doi` (Chen & Demir 2022, `10.3390/polym14071451`) is
  topically on-chemistry (polyphosphazenes) but its methods section actually uses **DREIDING**,
  not PCFF or any Class-II field, on Cl/F-substituted variants (PZ-DC, PZ-TFE, azido/nitrato) —
  none of which is the plain alkoxy chemistry PPHS targets. Density accuracy for DREIDING itself
  is mixed (+9.4% to -17%).
- The genuine PCFF-lineage evidence is COMPASS's 1998 phosphazene reparameterization
  (`10.1016/s1089-3156(98)00042-7`) — nonbonded params "initially transferred from PCFF" then
  reoptimized — but validated only on small molecules/liquids/crystals, not bulk amorphous
  polymer melts, and not on ethoxy substituents.

**Why:** this reconfirms (does not close) the class's own existing `ff_note` admission that "no
pcff-vs-experiment polyphosphazene validation paper has been located." Fresh WebSearch this round
was blocked entirely (session-wide 200/200 budget already exhausted before any PPHS query ran);
WebFetch fallbacks (PubMed, Semantic Scholar, Google) also returned nothing new.

**How to apply:** when re-auditing PPHS (or any class) and the WebSearch budget is already
exhausted session-wide, fall back to WebFetch against PubMed/Semantic Scholar/Google search URLs
before declaring a field ungrounded — it rarely finds new results but is nonzero-cost coverage.
Report the pre-existing gap honestly rather than fabricating support; PCFF for PPHS remains
admissibility-only (EMC can type it), not accuracy-validated. See [[feedback_publisher_webfetch_403_arxiv_fallback]] for related search-tooling notes.
