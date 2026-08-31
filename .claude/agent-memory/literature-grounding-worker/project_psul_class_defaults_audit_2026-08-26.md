---
name: project-psul-class-defaults-audit-2026-08-26
description: PSUL (PPS/polythioether) class-default DP/nchain re-audit findings, 2026-08-26
metadata:
  type: project
---

PSUL class defaults (dp_typical=40, dp_min=20, nchain=10 in guides/polymer_rules.json) are NOT
contradicted by any verifiable literature, but also not affirmatively supported -- no MD
convergence study of PPS/polythioether system size could be verified.

Candidates found and their fates:
- Chinese J. Polym. Sci. 2024, doi:10.1007/s10118-024-3072-1 ("Impact of Carbon Chain Structures
  in the Backbone on the Flexibility of Modified Polyarylene Sulfide Resins") -- MD study of PPS
  backbone modification, likely has DP/nchain in its methods section, but Springer paywalled
  every WebFetch attempt (login redirect). Worth retrying if Springer access ever becomes
  available.
- A 2025 ScienceDirect PPS drug-adsorption MD paper: search snippet claims DP=5 x nchain=10 cell
  -- far below class dp_typical=40, but for an unrelated adsorption purpose (no Tg/K convergence
  claim), and unverified (ScienceDirect blocked). Cannot be used to move the defaults either way.
- A 2023 ScienceDirect PPS entanglement/crystallization paper: experimental (rheology) Me
  354-1188 g/mol, no MD component -- out of scope per this agent's own instructions (never backs
  a value), also unverified.

**Why:** Elsevier (ScienceDirect) and Springer both blocked WebFetch on every PPS-specific
candidate found in this audit, on top of the already-known ACS/RSC/MDPI/ResearchGate block
pattern -- see [[feedback_publisher_domains_block_webfetch]]. No open-access (arXiv/PMC) PPS MD
paper exists in the literature as of this search.

**How to apply:** If re-auditing PSUL/PPS again, retry the Chinese J. Polym. Sci. 2024 DOI first
(most promising unverified lead) via any newly-available access route before re-running the full
search. Otherwise, this class remains an open literature gap like PVC/PVDF/PHYC re-audits.
