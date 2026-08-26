---
name: project-ppnl-class-defaults-audit-2026-08-26
description: PPNL (PPV/conjugated polymer) class dp_typical/nchain re-audit against P3HT CGMD DP-floor evidence
metadata:
  type: project
---

PPNL class defaults (dp_typical=25, dp_min=20, nchain=10) were audited 2026-08-26 for PPV
(SMILES `*C=Cc1ccc(*)cc1`).

- The class's own primary PPV citation, Venkatanarayanan & Ananth 2016 (DOI
  10.1002/mats.201600006, already the `ff_justification_doi` for PPNL), is Wiley-paywalled with
  no OA copy (checked Unpaywall, Semantic Scholar, Crossref abstract) -- DP/nchain used in that
  study remain unverifiable, consistent with the pre-existing `ff_note` caveat about this paper.
- Best verified evidence found: Yoshimoto et al. (arXiv:2010.01962, published as
  10.1021/acs.macromol.0c02278, *Macromolecules* 2021) -- coarse-grained MD of P3HT:C60
  composites, explicitly a PPNL-class example ("P3HT-like"). Read the full arXiv PDF directly
  (ACS version blocked, preprint content verified). States, citing Tummala et al.: "P3HT
  oligomers containing at least 50 monomer units are required to observe elastic behavior in MD
  simulations, while even longer chains are required for appropriate representation of molecular
  chain entanglements." They ran DP=50-150, nchain=300-900 (CG particles).
- This is a real, reportable DISAGREEMENT signal: PPNL's dp_typical=25 is HALF the DP=50 floor
  this related conjugated-polymer chemistry needs just to show elastic behavior at all -- but
  it's cross-chemistry (thiophene P3HT vs phenylene-vinylene PPV) and cross-forcefield (CG vs
  atomistic PCFF), so confidence stayed medium, convergence_basis="class_analogy", and nchain was
  left null (their 300-900 CG-chain count reflects CG box-size/self-entanglement-avoidance needs,
  not an atomistic-PCFF nchain recommendation -- do not transfer that number directly).
- Wrote to `data/PPNL_rules_audit/raw/literature_grounding_system_size.json`, ingested 1 record
  to the persistent store.

See also [[feedback_publisher_domains_block_webfetch]] (confirmed again: Wiley blocks like
ACS/RSC/MDPI). New technique that worked here: `export.arxiv.org` requires https (http gets a
301 redirect that curl silently drops query params on) -- use `https://export.arxiv.org/api/query`
directly for arXiv API searches when WebSearch budget is exhausted.
