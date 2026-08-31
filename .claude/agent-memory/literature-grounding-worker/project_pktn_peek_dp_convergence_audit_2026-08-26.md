---
name: project-pktn-peek-dp-convergence-audit-2026-08-26
description: PKTN (PEEK) class-default DP/nchain re-audit findings, 2026-08-26
metadata:
  type: project
---

PKTN class defaults (`dp_typical=50`, `dp_min=50`, `nchain=8`) were re-audited against published
MD literature for PEEK on 2026-08-26. **Neither confirmed nor contradicted** by anything
verified — the defaults rest entirely on the Patrone 2016 stiff-backbone DP>=50 Fox-Flory rule
already in `polymer_rules.json`'s global notes, not on a PEEK-specific MD convergence study.

Findings:
- The one **verified** PEEK MD paper (COMPASS II Tg study, PMC7285100, already cited in
  polymer_rules.json for its Tg=424-429K value) uses a fixed DP=4 tetrameric oligomer (o-PEEK,
  136 atoms/oligomer) in a 40-oligomer supercell, with **no DP convergence sweep performed at
  all**. Irrelevant to validating dp_typical=50.
- The single most relevant PEEK-specific DP-effect paper — Mittal & Parashar 2024, *Phys. Chem.
  Chem. Phys.*, "Effect of the degree of polymerization, crystallinity and sulfonation on the
  thermal behaviour of PEEK: a molecular dynamics-based study", DOI 10.1039/d4cp02259a — is
  **blocked (RSC 403)** at both the DOI-resolve and direct pubs.rsc.org URL. Abstract only
  (via Semantic Scholar / Europe PMC metadata) confirms DP "significantly affects thermal
  conductivity" but gives no specific DP values or plateau claim. Good retry candidate if
  RSC access is ever available — try an author/ResearchGate mirror next time.
- No PEEK-specific packing-length/characteristic-ratio (C-infinity) source found via crossref
  search for the priority-2 (packing-length-to-Me) bulk_modulus route — Fetters/Lohse/Milner/
  Graessley 1999 (10.1021/ma990620o) is the general theory paper but has no PEEK-specific input
  to feed it.
- **Note on tooling**: this session's WebSearch budget was already exhausted (200/200) before
  this task started — substituted `https://api.crossref.org/works?query=...` (WebFetch of the
  Crossref REST API) as a search fallback, which worked well and surfaced the Mittal & Parashar
  paper directly. Worth reusing this pattern if WebSearch is ever unavailable again.

See also [[project_phyc_class_defaults_audit_2026-08-26]], [[project_pcbn_bpapc_dp_convergence_audit_2026-08-26]]
for the same "confidence stays low despite non-contradiction" pattern in other class re-audits.
