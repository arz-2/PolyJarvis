---
name: pmma-atactic-vs-isotactic-smiles-disambiguation
description: How to tell atactic vs isotactic PMMA apart from the bare SMILES, and which Tg target applies to each
metadata:
  type: project
---

The plain, no-stereocenter PMMA SMILES `*CC(*)(C)C(=O)OC` builds ATACTIC PMMA. This is a
different chemistry than the isotactic SMILES `*[C@@](C)(C(=O)OC)C*` covered by
[[pmma-isotactic-tg-and-cooling-rate]] -- do not apply that memory's 320-333 K isotactic Tg band
to an atactic run. For atactic PMMA (EvidenceStoreVerify1 run, 2026-08-25):

- **Tg target 383 K** (from Polymer 2022, 10.1016/j.polymer.2022.125044, OPLS-AA MD study's own
  cited experimental validation target for non-tacticity-resolved/atactic PMMA) is consistent
  with, and corroborates, `polymer_rules.json`'s PACR.experimental_tg_K.PMMA = 378 K class
  default -- unlike the isotactic case, no downward Tg-target shift is warranted here.
- Cooling rate ~1 K/ns still applies (same as the isotactic finding) -- both the Macromolecules
  2018 stereoregular-PMMA/graphene paper (10.1021/acs.macromol.8b01160) and the Polymer 2022
  OPLS-AA paper (10.1016/j.polymer.2022.125044) use ~1 K/ns regardless of tacticity.
- Full text of both papers was Cloudflare/403-blocked on this pass (could not re-verify the exact
  numeric cooling-rate figure by fresh full-text read) -- the 1 K/ns and 383 K claims rest on DOI
  resolution + title match this pass, plus a prior session's (2026-08-23) full-text verification
  recorded in [[pmma-isotactic-tg-and-cooling-rate]]. Flag this residual-risk pattern (paywalled
  ACS/Elsevier full text) if it recurs -- unpaywall/semantic-scholar APIs did not surface OA copies
  for either DOI.
- No PMMA-specific electrostatics (pppm vs lj_cut) statement or atactic-specific density target
  was found accessible in this pass either -- both stayed low-confidence/null in the output.

See [[docs-ff-selection-literature-workflow]] for the check-first-then-search procedure.
