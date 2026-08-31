---
name: pura-rules-audit-gap-reconfirmed
description: PURA class rules-audit re-confirmed no MD study validates GAFF2/GAFF2_mod on pure polyurea; two promising ScienceDirect leads dead-ended
metadata:
  type: project
---

2026-08-26 PURA class-default re-audit (`data/PURA_rules_audit/`) reproduced the same gap already
admitted in the class's `ff_note`: no peer-reviewed MD study of pure urea-linkage polyurea
(GAFF2/GAFF2_mod, electrostatics, cooling rate, density/Tg targets, or CTE) could be found or
verified. Two store hits from a prior session remain the closest evidence and are both
non-corroborating: a 2025 MDPI "polyureas" paper (10.3390/polym17010107) is actually a
urea-urethane HYBRID elastomer with 24 wt% diol soft segments, simulated with COMPASS not GAFF2;
a 2023 GAFF/OPLS urea benchmark (10.1021/acs.cgd.3c00785) is a small-molecule urea CRYSTAL study
(GAFF2 overestimates crystal density +7.4%) that says nothing about the amorphous polymer melt.

Two additional promising ScienceDirect leads surfaced this round but could not be verified:
a PDMS-modified polyaspartate-polyurea Tg/cooling-rate MD paper (S0032386124003513) and a
Grujicic-style "Deformation of polyurea: Where does the energy go?" MD/thermal-expansion paper
(S0032386116309405) — both 403'd on WebFetch (see
[[feedback_publisher_webfetch_403_arxiv_fallback]]) with no arXiv/open-access mirror found before
the session's WebSearch budget (200/200) was exhausted.

**Why:** PURA is EMC-inadmissible (missing {na,c_2} amide-N increment) and routed to RadonPy/GAFF2_mod
as the only build path — this is an engineering necessity, not a literature-validated accuracy
claim, and repeated audits keep confirming that gap rather than closing it.

**How to apply:** Future PURA audits should try to access the two ScienceDirect leads above via a
non-WebFetch route (e.g. an author's institutional repository, ResearchGate PDF link, or ask the
user for direct access) before re-running the same searches that already dead-ended twice. If
still unreachable, don't keep re-spending full search budget on this class — the gap is
well-established at this point and the honest confirmation is itself the correct, actionable
output for the planner (fall back to `polymer_rules.json` defaults).
