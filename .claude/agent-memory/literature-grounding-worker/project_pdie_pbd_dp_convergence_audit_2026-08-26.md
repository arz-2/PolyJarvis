---
name: project-pdie-pbd-dp-convergence-audit-2026-08-26
description: PDIE (polydiene/PBD-PI) class-defaults re-audit findings for system size (D-04)
metadata:
  type: project
---

Ran the class-defaults re-audit for PDIE (dp_typical=100, dp_min=50, nchain=20) requested
2026-08-26. Two findings:

1. dp_typical=100/nchain=20 are NOT contradicted. Best quantitative anchor: Lyubimov & Guenza
   2013 (arXiv:1301.0166, "Theoretical Reconstruction of Realistic Dynamics of Highly
   Coarse-Grained cis-1,4-Polybutadiene Melts") — verified by direct PDF read, not just search
   snippet. Cites Tsolou/Harmandaris/Mavrantzas UA-MD PB samples at N=32,56,128,320 backbone
   carbons (DP = N/4 ≈ 8,14,32,80 repeat units, since butadiene backbone repeat = 4 carbons).
   States entanglement Ne(shear) ≈ 330 backbone carbons ≈ DP 83 repeat units for PB, and that
   deviation from Rouse N^-1 diffusion already starts near N≈100 backbone carbons (DP≈25).
   dp_typical=100 clears both the Fox-Flory Tg floor (DP≥20) and the entanglement-onset DP≈83
   documented for this polymer's own MD lineage — the strongest atomistic PB study this paper
   draws on (DP≈80) doesn't even reach that far.

2. CORRECTION to existing polymer_rules.json PDIE note: "DP=50-200 studied by polyisoprene MD:
   mechanical properties converge above DP=50 (PMC9698502)" is NOT supported by that source.
   PMC9698502 = Chen et al. 2022, Polymers, DOI 10.3390/polym14224950 — cis-polyisoprene OPLS-AA
   NEMD at DP=50,100,150,200: max tensile strength/modulus INCREASE CONTINUOUSLY across the
   whole range (0.164→0.271 GPa), no plateau reached. Only thermal conductivity (not mechanical)
   converges. Doesn't change the numeric recommendation (dp_typical=100 still clears DP=50
   regardless) but the citation/claim itself should be fixed or removed from polymer_rules.json.

Also confirms [[feedback_publisher_domains_block_webfetch]]: AIP (pubs.aip.org) 403s WebFetch
just like ACS/RSC/MDPI — the Tsolou 2006 JCP DOI resolved (doi.org → AIP redirect, Unpaywall/
Semantic Scholar metadata match) but full text/abstract was never independently read, so its
specific "32-chain C128" system-size claim (found only via search-engine summaries) was NOT used
to back dp_typical/nchain — logged as verified:false, context only. arXiv PDF direct-read
worked fine and was the actual source of the verified claim.

Ingest note: the arXiv source has no DOI, so `protocol_evidence.py ingest` rejected it
("missing 'doi'") even though verified:true — only the DOI-bearing PMC9698502 correction record
made it into the persistent store (records_added=1). The store currently can't hold DOI-less
preprint evidence even when it's the stronger/primary finding — future audits on other
arXiv-only-verified polymers will hit the same gap.
