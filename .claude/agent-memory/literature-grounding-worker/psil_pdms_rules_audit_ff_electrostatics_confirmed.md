---
name: psil-pdms-rules-audit-ff-electrostatics-confirmed
description: PSIL (PDMS) rules-audit confirmed OPLS-AA/PPPM defaults; cooling rate/density/Tg/CTE remain ungrounded by MD literature due to PDMS's Tg being far below any studied MD temperature range
metadata:
  type: project
---

2026-08-26 PSIL/PDMS class-default re-audit (data/PSIL_rules_audit/).

**Forcefield (opls/2024/opls-aa)**: confirmed via same store hit used before (DOI
10.1021/acs.jpcb.4c08471, PDMS 5-force-field benchmark). Explicitly re-verified the DREIDING
comparison the audit specifically asked about: OPLS-AA density RMSE 0.0414 g/cm3 vs DREIDING
0.1337 g/cm3 — OPLS-AA is the clearly better of the two EMC-admissible options (PCFF is
mechanically inadmissible, not a literature question). No change recommended.

**Electrostatics (pppm)**: NEW finding this round, ingested into the store (1 record added).
Full text (via PMC mirror PMC11831649, since pubs.acs.org WebFetch 403'd as usual — see
[[feedback_publisher_webfetch_403_arxiv_fallback]]) confirms the paper's OPLS-AA all-atom PDMS
model uses PPPM/Ewald for long-range Coulomb (1.1 nm cutoff), not a bare cutoff scheme. Confirms
the class's current `electrostatics: pppm` default.

**Gap found**: cooling_rate_K_per_ns, density_target_gcm3 (numeric), tg_target_K, cte_glass_melt
all remain ungrounded by any MD-simulation source. Root cause specific to PDMS: its Tg (~148 K,
exceptionally low due to the flexible Si-O backbone) sits far below the temperature range any
found MD study actually simulates (this benchmark paper: 250-450 K, entirely rubbery/melt state).
No same-polymer MD study that thermally sweeps through or below PDMS's Tg was found via
arXiv-API/PubMed fallback searches (WebSearch tool budget was exhausted mid-session, which
blocked a fuller sweep — re-run those fields with fresh WebSearch budget if this matters for a
real run rather than a rules audit). This is a genuine gap, not contradiction — the class's
existing thermal-protocol defaults (tg_rates [10,25,50] K/ns, exp_tg 148K, density target 0.97
g/cm3 RT) were NOT corroborated NOR contradicted this round.

See also [[poxi_peo_rules_audit_ff_cooling_rate_findings]] for a similar pattern (verified
same-chemistry cooling-rate finding vs. ungrounded fields in one audit).
