---
name: pimn-linear-pei-rules-audit-gap-reconfirmed
description: PIMN class default (PCFF/pppm) audited against linear PEI (*CCN*) specifically -- no bulk MD literature validates it for the aliphatic-amine chemistry, only for the aromatic-etherimide (Ultem) side
metadata:
  type: project
---

2026-08-26 rules-audit of PIMN (Polyamine/Polyetherimide/Epoxy class) against its aliphatic member,
linear poly(ethylenimine) (`*CCN*`), not the aromatic polyetherimide (Ultem) exemplar the class's
only verified FF citation (Wen2020, 10.1002/pol.20200050) actually covers.

**Finding: the class's existing ff_note gap is real and not closeable with currently-accessible
literature.** polymer_rules.json's own PIMN ff_note already states this ("linear poly(ethylenimine)
remains uncited, a genuine open gap") -- this audit reproduces that conclusion rather than resolving
it, after a real search effort.

Two genuinely on-chemistry candidates surfaced (via Crossref/Semantic-Scholar bibliographic search,
not WebSearch -- session's WebSearch budget was exhausted on this task):
- Dong et al. 2001, 10.1016/S0032-3861(01)00234-8, "MD simulations and structural comparisons of
  amorphous poly(ethylene oxide) and poly(ethylenimine) models" (Polymer journal) -- exactly on-topic
  (amorphous PEI cell MD) but ScienceDirect 403s WebFetch and no Unpaywall OA copy exists; force
  field/density/Tg unverifiable.
- Kawagoe et al. 2019, 10.1016/j.polymer.2019.121721, "linear and branched polyethylenimine" MD for
  thermal conductivity -- also on-chemistry (linear PEI specifically) but same access wall; abstract
  (via Semantic Scholar) doesn't state the force field either.
- The one VERIFIED same-chemistry hit, Ondrejcek/Vazdar-style CHARMM-PEI paper (10.1002/jcc.24890,
  Crossref abstract directly confirms "development of a new atomistic (CHARMM) FF for PEI"), is a
  dilute solvated/protonated-polyelectrolyte gene-delivery study -- doesn't validate OR contradict
  PCFF for bulk amorphous density/Tg use, since it's a different force field for a different regime.

**Net call: kept PCFF/pppm class default** (admissibility already independently confirmed via
forcefield.py select; no literature argues against it) but flagged density/Tg/cooling-rate/CTE
targets for linear PEI as still MD-literature-unvalidated defaults.

See also [[feedback_publisher_webfetch_403_arxiv_fallback]] -- ScienceDirect/ResearchGate 403s were
the binding constraint here too; Crossref's `abstract` field (direct publisher metadata via API) and
Semantic Scholar's stored abstract were usable as a fallback discovery/scoping tool when WebFetch on
the publisher page itself failed, though neither counts as full verification of in-paper technical
claims (FF name, numeric density/Tg) the way a WebFetched full text would.
