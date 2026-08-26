---
name: pest-class-defaults-audit-2026-08-26
description: PEST (PET/PLA/PCL/PBT) polymer_rules.json dp_typical=50/dp_min=25/nchain=10 re-audit outcome — not contradicted, no SCREENING-dp caveat needed (opposite of PSTR/PACR)
metadata:
  type: project
---

Re-audit (2026-08-26, `data/PEST_rules_audit/raw/literature_grounding_system_size.json`)
of `guides/polymer_rules.json:classes.PEST` (dp_typical=50, dp_min=25, nchain=10) against
published PET MD literature, using PET as the representative member.

**Verdict: current defaults are not contradicted, and PEST correctly carries no
SCREENING-dp caveat.** This is the opposite situation from [[project_pmma_isotactic_dp_convergence]]
(PS: DP@Me=160 > dp_typical=40; PMMA: DP@Me>=200 > dp_typical=50, both caveated in
polymer_rules.json) — for PET, DP@Me ≈ 7.5 (entanglement_Me_gmol=1450 g/mol from Mark 2007,
already in the rules, divided by repeat-unit MW ~192 g/mol) sits far BELOW dp_typical=50
(~6.7x below), so no dedicated-higher-DP-for-accurate-K caveat is warranted for this class.
dp_typical=50 also clears D-04's Fox-Flory DP>=20 floor 2.5x over.

**Sources found, both ingested to `docs/protocol_evidence_system_size.json` (2 records added):**
- Golmohammadi et al. 2020, J. Chem. Phys. 152, 114901 (DOI 10.1063/1.5145142) — CG-MD PET,
  chains of 100 repeat units used to probe entanglement-dominated dynamics; Rouse-to-reptation
  crossover onsets at that length but full separation needs much longer *time*, not necessarily
  longer chains. Verified via Semantic Scholar API abstract (paperId
  c00ae11ac7c60c5d8b697b3df3e5334be5b94eef) + Crossref DOI cross-check — ACS/AIP full-text
  itself 403'd, only the API-sourced abstract was directly read. Contextual only; does not set
  a specific DP/nchain number on its own.
- Sangkhawasi et al. 2022, Polymers 14(6), 1161 (DOI 10.3390/polym14061161) — verified via
  direct PMC fetch. Single-chain (no nchain) all-atom OPLS-AA MD, DP=100, Tg=345K vs
  ~342K prior prediction. No DP-sweep/convergence test in-paper — explicitly noted as neither
  supporting nor contradicting dp_typical=50.

**Open verification lead (NOT ingested — verified:false):** Wang, Keffer, Nicholson & Thomas
2010, Macromolecules 43(24) 10722-10734 (DOI 10.1021/ma102084a) — search-engine summaries
(consistent across 2 independent queries) claim CG PET simulated up to DP=50, with
entangled-melt-matching scaling exponents (0.51/0.50/-2.00) at the longest (DP=50) chains —
this would be a direct, specific match to the current dp_typical=50 default, the strongest
possible evidence found this round. Could NOT verify: ACS (403), ResearchGate (403), Semantic
Scholar API (abstract elided by publisher), Unpaywall (no OA copy exists). Per this worker's
own rule an unverified source can't back dp_typical, so it was left out despite the numeric
match. **How to apply:** if re-auditing PEST again, try an institutional/library proxy or a PDF
mirror specifically for ma102084a — resolving it would upgrade this from "not contradicted" to
"directly confirmed."

**Why this matters:** demonstrates the class-defaults audit can produce a genuinely positive,
reportable "agreement" outcome (per the calling session's explicit request) without needing to
invent or inflate a number — see [[project_phyc_class_defaults_audit_2026-08-26]] for the same
pattern on PHYC. Also a clean example of the store's `verified:false` sources being correctly
excluded from `ingest_protocol_evidence.py` (2 of 3 sources ingested, 1 skipped).
