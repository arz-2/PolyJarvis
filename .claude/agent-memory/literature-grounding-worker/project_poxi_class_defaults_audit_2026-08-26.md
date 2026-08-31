---
name: poxi-class-defaults-audit-2026-08-26
description: POXI (PEO/PPO/PVME) class-default DP/nchain re-audit against MD literature
metadata:
  type: project
---

Audited `guides/polymer_rules.json` classes.POXI dp_typical=100/dp_min=50/nchain=10 against
published MD literature for PEO (2026-08-26).

**Finding: class defaults for DP are NOT contradicted.** The persistent evidence store already
held an exact-SMILES peer-reviewed hit (Tsalikis et al. 2021, doi:10.3390/polym13224049,
`record_id 253fc837098c`) verifying DP=50/nchain=20 all-atom MD reproduces experimental PEO
density and a physically reasonable Tg, cross-validated against two other independent MD
groups (Luo & Jiang; Tsalikis UA-PEO) also using N~50. POXI's dp_min=50 matches this exactly;
dp_typical=100 doubles it — no under-specification.

**Gap found: nchain.** The verified source uses nchain=20; POXI's class default is nchain=10
(half). No evidence nchain=10 specifically fails to converge, but it is unvalidated relative to
what was actually published — worth flagging to the planner as a minor open gap, not a defect.

**bulk_modulus: no direct evidence found.** No MD study measuring DP/nchain-vs-K convergence for
PEO located. Attempted to verify a documented PEO entanglement Me (~1600-2000 g/mol, widely
cited via Fetters reviews in search snippets) against a resolvable primary source — WebFetch of
Fetters 1999 (doi:10.1002/(SICI)1099-0488(19990515)37:10%3C1023::AID-POLB7%3E3.0.CO;2-T) states
the general packing-length power law (Me/rho=218p^3) but the accessible abstract/reference text
did not name PEO among the tested polymer set, so the Me number stayed unverified — marked
`verified: false` in the output. See [[feedback_publisher_domains_block_webfetch]] — Wiley
abstract pages likewise expose only partial text.

Output: `data/POXI_rules_audit/raw/literature_grounding_system_size.json`.
