---
name: project-pimn-pei-dp-convergence-audit-2026-08-26
description: PIMN (linear PEI) class-default DP/nchain re-audit 2026-08-26 -- no verifiable MD source found, neither confirms nor contradicts dp_typical=20/nchain=10
metadata:
  type: project
---

Audited polymer_rules.json PIMN class defaults (dp_typical=20, dp_min=20, nchain=10) against
published MD literature for linear poly(ethylenimine) (SMILES `*CCN*`).

Result: zero verified sources found, in either direction.

- Only on-topic candidate: Dong, Hyun, Durham, Wheeler, "Molecular dynamics simulations and
  structural comparisons of amorphous poly(ethylene oxide) and poly(ethylenimine) models",
  *Polymer* 42(18) 7809-7817 (2001), DOI 10.1016/S0032-3861(01)00234-8. Confirmed via
  Crossref/Unpaywall metadata to exist and be on-topic (amorphous-cell MD, PEO vs. linear PEI),
  but Unpaywall reports closed access and ScienceDirect/linkinghub blocked WebFetch — could not
  read the actual DP/nchain/convergence content, so left `verified: false`.
- No entanglement-Me or packing-length/C-infinity source found for PEI either (priority-2
  fallback also came up empty).
- Note the class entry's own stated rationale for dp_typical=20 ("short segment between
  crosslinks for epoxy network model; linear polyimine also uses ~20") is an unreferenced
  carryover from the DGEBA-amine epoxy-crosslink side of this dual-scope class, not an
  independent linear-PEI citation — flagged in output notes but not something this audit could
  resolve either way.

**Why:** linear PEI has essentially no dedicated bulk-amorphous atomistic MD literature
discoverable via Crossref/Unpaywall/Semantic Scholar search — the PEI literature that *does*
exist heavily skews toward branched-PEI gene-delivery/siRNA-complexation coarse-grained (Martini)
work, a structurally and methodologically different subfield.

**How to apply:** if this SMILES/class comes up again, don't re-search from scratch — the Dong
2001 paper is the only lead and it needs institutional/paywall access to actually verify (try
requesting the PDF directly if a subscription route becomes available). Otherwise, treat PIMN's
dp_typical=20/nchain=10 as neither confirmed nor contradicted; same class of finding as
[[project_panh_class_defaults_audit_2026-08-26]] and [[project_pura_dp_convergence_audit_2026-08-26]]
(sparse/absent literature, not a search failure to keep reattempting).
