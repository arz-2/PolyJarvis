---
name: panh-ff-citation-mismatch
description: PANH class's ff_justification_doi (10.1021/acsapm.0c00524) does not actually support its PCFF claim
metadata:
  type: feedback
---

`guides/polymer_rules.json` classes.PANH.ff_justification_doi = `10.1021/acsapm.0c00524`
("High-Throughput Molecular Dynamics Simulations and Validation of Thermophysical
Properties of Polymers" by Afzal et al., ACS Appl. Polym. Mater. 2021). Verified via
WebFetch (DOI resolves) and multiple WebSearches: this paper is a 315-polymer
high-throughput screen using the **OPLS3e** force field, not PCFF, and there is no
evidence (abstract, figshare collection page, search snippets) that it covers
poly(sebacic anhydride) or any polyanhydride. It does not actually validate PCFF for
PANH.

**Why:** The literature-grounding-worker protocol requires verifying every cited DOI
resolves AND states the claim attributed to it before citing it as support. This DOI
resolves but does not state the PCFF-for-polyanhydride claim it's attached to in
polymer_rules.json — a pre-existing mismatched citation, not something I introduced.

**How to apply:** Never treat an existing `*_justification_doi` field in
polymer_rules.json as pre-verified — check it the same way as any new candidate source
before reusing it as backing evidence. If found unverified/mismatched (as here), flag it
via `verified: false` with an explanatory claim in the output JSON's sources array and
surface it in `notes`/`dominant_uncertainty`, but do NOT silently edit the existing class
entry (guard rail: only ever append brand-new class keys, never modify an existing
entry's fields, even to fix a bad citation) — that's out of scope for this worker; leave
correction to whoever owns polymer_rules.json curation.
