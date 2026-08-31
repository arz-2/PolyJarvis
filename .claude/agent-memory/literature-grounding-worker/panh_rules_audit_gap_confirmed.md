---
name: panh-rules-audit-gap-confirmed
description: PANH (polyanhydride) class-default re-audit found zero MD/simulation literature for any polyanhydride chemistry; existing ff_note gap reproduced, not closed
metadata:
  type: project
---

Re-audited PANH class defaults (poly(sebacic anhydride), `*OC(=O)CCCCCCCCC(*)=O`) on 2026-08-26.
Store query (`query_protocol_evidence.py --store ff`) returned zero exact_smiles/exact_class hits
for any field — only `similar_class` PEST (polyester) analogs at similarity 0.667. Fresh search
(CrossRef + Semantic Scholar APIs, WebSearch budget was exhausted this session) for
polyanhydride + MD/force-field/amorphous-cell/glass-transition returned only experimental
synthesis/degradation papers and an unrelated sebacic-acid-as-nanoparticle-surfactant paper — no
on-chemistry MD study exists.

**Why:** `guides/polymer_rules.json` PANH's own `ff_note` already stated "No PCFF/COMPASS/Class-II
density or Tg source for any polyanhydride has been located despite a dedicated search" — this
session's fresh search corroborates rather than contradicts that claim, across multiple query
angles (general polyanhydride MD, PCFF/COMPASS-specific, CPH/CPP-specific, Afzal2021 verification
attempt).

**How to apply:** If a future PANH-class run or rules-audit re-invokes this worker, don't expect a
fresh search to close this gap — it has now failed twice (original + this audit). Treat PANH FF/
electrostatics/cooling-rate/density/Tg grounding as permanently `confidence: low` until either (a)
a genuinely new polyanhydride MD paper is published, or (b) an internal PolyJarvis PANH run is
ingested via `ingest_internal_run_evidence.py` (which is the only path that can ever produce an
`internal_validated_run` trust tier for this class). Also: `Afzal2021` (10.1021/acsapm.0c00524,
the class's `ff_justification_doi`, an OPLS3e 315-polymer Tg screen) could not be independently
verified to include/exclude polyanhydride coverage this session — ACS publisher page and ChemRxiv
preprint both 403'd WebFetch (see [[feedback_publisher_webfetch_403_arxiv_fallback]]); this citation
remains unverified-by-me, not newly confirmed absent.
