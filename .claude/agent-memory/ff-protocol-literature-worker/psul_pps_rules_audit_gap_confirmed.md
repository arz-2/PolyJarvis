---
name: psul-pps-rules-audit-gap-confirmed
description: PSUL/PPS rules-audit (2026-08-26) re-confirmed the PCFF-vs-experiment MD validation gap is genuine, not a stale search
metadata:
  type: project
---

Re-audited PSUL class defaults (forcefield=PCFF, electrostatics=pppm, tg_rates=[25,50,100],
exp Tg 358K, exp density 1.35 g/cm3) against fresh 2026-08-26 literature search plus the
persistent evidence store (`docs/protocol_evidence_ff.json`).

Finding: the store held exactly one PSUL/PPS hit — a 2024 Chinese J. Polym. Sci. paper
(10.1007/s10118-024-3072-1) that studies PPS directly but runs **COMPASS II, not PCFF**, and
reports no quantitative density/Tg for the unmodified-PPS baseline (only a qualitative trend
across alkyl-substituted variants). Fresh searches across FF/electrostatics/cooling-rate/
density-Tg-target/CTE angles reproduced only this same hit plus unrelated material (ReaxFF
pyrolysis study, experimental-only DSC/DMA Tg papers, generic aromatic-glass MD methodology).
No new verifiable source was found for any field.

**Why:** confirms the class's own `ff_note` admission ("no PCFF-vs-experiment polythioether/pps
literature has been located despite a dedicated search") is not a stale/lazy prior claim — a
second, independent search pass genuinely turns up nothing more. This is a real, durable gap in
the literature, not a search-effort artifact.

**How to apply:** if PSUL/PPS comes up again for grounding or a rules audit, don't expect a
fresh search to surface new PCFF-specific validation — the COMPASS II paper is very likely the
best on-chemistry MD hit available. Any future win here would most plausibly come from a new
paper being published, not from searching harder with the same query angles already tried
(FF name + MD, electrostatics/PPPM, cooling rate, density/Tg target, CTE — all tried this round).
See also [[pacr_rules_audit_pmma_density_tg_corroboration]] and
[[pstr_rules_audit_ps_ff_density_tg_corroboration]] for the pattern of rules-audit sessions on
other classes, where fresh searches DID surface new corroborating evidence — PSUL is the
counter-example where the gap held.
