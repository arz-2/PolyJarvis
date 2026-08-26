---
name: project-pamd-class-defaults-audit-2026-08-26
description: PAMD (Nylon-6/polyamide) class dp_typical/nchain re-audit outcome and the PA66 source used
metadata:
  type: project
---

PAMD class defaults (dp_typical=50, dp_min=25, nchain=10 in guides/polymer_rules.json) are NOT
contradicted by literature. No dedicated MD chain-length convergence sweep (density/Tg/modulus vs
DP) exists for Nylon-6 or Nylon-6,6 in what's searchable/verifiable. Best verified source: Gadelrab,
Kech, Cruz, "Atomistic Modeling of the Hygromechanical Properties of Amorphous Polyamide 6,6",
J. Phys. Chem. B (2026), DOI 10.1021/acs.jpcb.5c07710 — ACS page 403s (per
[[feedback_publisher_domains_block_webfetch]]) but content was fully readable via its arXiv mirror
(arxiv.org/html/2603.14569, same title/authors) so treated as verified peer_reviewed_doi. That
paper's own bulk MD used 12 chains x 80 monomers (18.1 kg/mol), justified only against a cited
literature Me~2 kg/mol for PA66 (Mnc = 3-5*Me) — no in-paper DP sweep. Using that Me and PA66's
~226 g/mol repeat unit, DP@Me ~9; for Nylon-6's ~113 g/mol repeat unit, DP@Me ~18 — both comfortably
below PAMD's dp_min=25/dp_typical=50, so the class defaults clear the D-04 DP>=20 Fox-Flory floor
even though the one verified paper itself ran a larger system (DP=80/nchain=12) without proving 50
is a true minimum via its own sweep. Wrote this finding to the persistent evidence store
(docs/protocol_evidence_system_size.json, 1 record added, run PAMD_rules_audit).
