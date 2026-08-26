---
name: poxi-peo-rules-audit-ff-cooling-rate-findings
description: POXI/PEO polymer_rules.json re-audit (2026-08-26) -- pppm/density/tg defaults confirmed, forcefield and cooling-rate flagged
metadata:
  type: project
---

Re-audited POXI class defaults (`guides/polymer_rules.json`, currently `preferred_ff="pcff"`) against
fresh full-text-verified MD literature for PEO (`*CCO*`). Output:
`data/POXI_rules_audit/raw/literature_grounding_ff_protocol.json`.

**Confirmed AGREEING with current defaults** (re-verified independently, not just carried forward):
- electrostatics=pppm: both verified PEO papers (10.3390/polym13224049 via PMC8618988 full text,
  10.1039/d4ra04898a) explicitly use Ewald/PPPM.
- density_target: literature range [1.07,1.27] g/cm3 @300K brackets the rules' 1.10-1.21 g/cm3.
- tg_target: literature range [158,233]K (10.3390/polym13224049's own cited lit range) brackets the
  rules' PEO exp Tg=206K.

**Flagged, not fixed** (advisory only, this was a re-audit not a plan):
- forcefield: PMC full-text access found OPLS-AA (2 papers, one PMC-confirmed) and GAFF as the
  literature-verified choices for bulk PEO/PEG density/Tg MD work this session; the class's PCFF
  default has NO session-verified same-chemistry paper behind it -- the one PCFF-family candidate
  (PCFF+, 10.1021/acs.macromol.1c01028, PEO/PTHF Na-electrolyte MD) is a hard ACS 403 on both the
  DOI redirect and its own CC-BY open-access copy (confirmed via Unpaywall), so it could not be
  full-text verified despite resolving and being genuinely open-access by license.
- cooling_rate: the one full-text-verified PEO Tg-sweep study (10.3390/polym13224049, PMC) used a
  single rate of 4x10^9 K/s = **4 K/ns**, far slower than the class's current sweep
  `tg_rates_K_per_ns: [25,50,100]`. Same pattern as [[pmma_isotactic_tg_and_cooling_rate]] --
  verified PEO/PEG MD Tg literature clusters near single-digit K/ns, not tens-of-K/ns.
- cte_glass_melt: no verified source found this session (existing rules' Wu2011 alpha=8.08e-4
  citation is detailed but could not be re-verified full-text this session -- ACS 403).

Ingest result: 3 new records added to `docs/protocol_evidence_ff.json` (cooling_rate, tg_target,
PCFF+ unverified-candidate forcefield entry), 5 correctly skipped as duplicates of existing
PEG1-run store records folded via `origin_record_id`.

See also [[feedback_publisher_webfetch_403_arxiv_fallback]] -- PMC worked here where MDPI/ACS/RSC
direct fetches all 403'd; PMC is now confirmed as a reliable fallback route specifically (not just
arXiv) when a paper has a PMC mirror.
