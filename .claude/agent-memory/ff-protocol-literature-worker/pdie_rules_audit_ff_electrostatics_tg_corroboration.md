---
name: pdie-rules-audit-ff-electrostatics-tg-corroboration
description: PDIE (PBD/PI) class-default re-audit findings -- TraPPE-UA/lj_cut/Tg~181K all corroborated, CTE still ungrounded
metadata:
  type: project
---

2026-08-26 rules-audit of PDIE (SMILES `*CC=CC*`, cis-1,4-polybutadiene) confirmed the class's
current defaults rather than overturning them:

- **forcefield=TraPPE-UA**: medium confidence. Sharma2016 (10.1021/acs.jpcb.5b10789, the class's
  existing ff_justification citation) still resolves and topically matches, but its full text
  remains ACS-paywalled -- no session has yet independently confirmed TraPPE-UA's own numeric
  Tg/density error from that paper's actual data. Two other UA-family MD papers (OPLS-UA:
  10.3390/polym12051081; unspecified-UA: 10.3390/ma14247737) corroborate that apolar UA models
  generally reproduce PBD/PI density/Tg reasonably, which is same-family (not same-exact-field)
  support.
- **electrostatics=lj_cut**: high confidence, newly strengthened. Both 10.3390/polym12051081 and
  10.3390/ma14247737 explicitly confirm zero net charge on UA groups and LJ-only nonbonded
  (no PPPM/Ewald) for PBD/PI MD.
- **tg_target~181K**: medium-high confidence, newly strengthened via an unusual cross-check.
  10.3390/ma14247737 reports DMA Tg -71 to -73C (200-202K) and states DSC is typically ~20K
  below DMA -- reconstructing to ~180-182K DSC-equivalent, matching PDIE's
  `experimental_tg_K.PBD=181` almost exactly. Worth reusing this DMA-to-DSC offset trick for
  other rubbery/low-Tg classes where direct DSC MD papers are scarce.
- **density_target~0.90 g/cm3**: medium confidence. 10.1007/s00894-023-05658-6 (pcff+, not
  TraPPE-UA) reports ~2% density accuracy achievable for this exact chemistry, but its accessible
  text never states the absolute experimental number -- so the range I reported was NOT lifted
  from that paper, it was derived by applying +/-2% to the pre-existing class default. Flag this
  distinction in future PDIE audits rather than re-citing the ~2% figure as if it validates the
  0.90 number itself.
- **cte_glass_melt**: still ungrounded (low confidence, unchanged). A candidate CTE figure
  (~7.6e-4 K^-1 at 300K, likely from Krushev/Paul 10.1016/s0032-3861(01)00628-0, "Molecular
  dynamics simulation of cis-1,4-polybutadiene. 1.") surfaced via search snippet but ScienceDirect
  blocked WebFetch (403) -- excluded per verification protocol. If a future session has
  ScienceDirect/institutional access, this DOI is the next thing to try for PDIE's CTE.

See [[feedback_publisher_webfetch_403_arxiv_fallback]] -- ACS (pubs.acs.org), ScienceDirect,
MDPI, ResearchGate, PubMed, and Taylor & Francis all 403'd WebFetch this session; only
Crossref API (bibliographic lookup for DOI confirmation) and PMC (`pmc.ncbi.nlm.nih.gov`, not
the `ncbi.nlm.nih.gov/pmc` redirect form) worked reliably.
