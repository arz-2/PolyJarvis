---
name: phyc-class-defaults-audit-2026-08-26
description: PHYC (PE/PP/PIB) polymer_rules.json dp_typical=120/dp_min=60/nchain=20 re-audit outcome — not contradicted, K-side gap persists
metadata:
  type: project
---

Re-audit (2026-08-26, `data/PHYC_rules_audit/raw/literature_grounding_system_size.json`)
of `guides/polymer_rules.json:classes.PHYC` (dp_typical=120, dp_min=60, nchain=20) against
published PE MD convergence studies.

**Verdict: current defaults are not contradicted.** dp_min=60 comfortably clears D-04's
DP>=20 Fox-Flory floor; no verified MD source argues PE Tg needs more DP. Recommended
leaving defaults as-is rather than inflating against unverified evidence.

**What's new since [[project_pe_phyc_entanglement_dp_convergence]] (2026-08-24):**
- Re-confirmed Hoy/Foteinopoulou/Kröger PRE 2009 (arXiv:0903.2078) verified: PE entanglement
  stats are only "marginally" reliable for N=100-200 (Table I: Z=2.876 at N=140, Z=5.089 at
  N=250). dp_typical=120 sits *inside*, not above, that marginal band — worth flagging if the
  class ever wants a robust entanglement-based Me for context, but this is advisory-only for
  bulk_modulus (see [[feedback_bulk_modulus_convergence_not_entanglement]]) so it does not
  itself force a class-default change.
- New candidate found: Tschopp et al. 2013 (arXiv:1310.0728, DREIDING UA PE deformation MD)
  verified full-text — uses DP=1000/nchain=100 for entangled deformation, but different FF
  (DREIDING not TraPPE-UA) and no convergence test in-paper (cites prior work for the choice).
  Weak class-analogy context only.
- Tried and failed (still) to verify PHYC's OWN foundational citation: Ramos2015
  (10.1021/acs.macromol.5b00823, already in polymer_rules.json as ff_justification_doi) — ACS
  403's every attempt. Search snippets describe a C192 (DP=192) PE model, which if confirmed
  would exceed the class's own adopted dp_typical=120 — this is a real open question, not
  resolved this round. Also re-tried RSC C5RA21115H (still 403) and a new 2025 candidate
  (Soldera et al., SSRN 5046967 / ScienceDirect 10.1016/j.polymer.2025.128278, PE bulk-vs-
  isolated-chain Tg — directly on point but SSRN 403'd, ScienceDirect not attempted).

**Why:** publisher blocks (ACS/RSC/SSRN) mean the class's actual foundational Tg source's
chain length has never been independently confirmed, despite being the literal FF/Tg
justification already baked into polymer_rules.json.

**How to apply:** if re-auditing PHYC again, try the ScienceDirect URL for Soldera 2025
directly (not attempted this round — only SSRN was tried and blocked) and try PMC/institutional
mirrors for Ramos2015 macromol.5b00823 specifically, since resolving its actual DP would
settle whether polymer_rules.json's own foundational citation supports dp_typical=120 or
implies it should be nearer 192.
