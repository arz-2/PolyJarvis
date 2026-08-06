---
name: phal-ff-citation-chain-mismatch
description: PHAL (PVDF/PTFE/PCTFE) class ff_justification_doi points to a paper that isn't actually an OPLS-AA validation for this polymer
metadata:
  type: feedback
---

`guides/polymer_rules.json`'s PHAL class entry cites `ff_justification_doi: 10.1021/ma9918295`
(Byutner & Smith, Macromolecules 2000) as OPLS-AA justification, but that paper is actually a
bespoke quantum-chemistry-derived Buckingham exp-6 + point-charge force field for PVDF — not an
OPLS-AA parameterization at all. It is a strong source for PVDF's amorphous density validation
target (1.75-1.78 g/cm3 at 283 K) and for the PPPM/electrostatics requirement, but not for the
FF-family choice.

The real OPLS-AA lineage for PVDF's CF2 backbone is Watkins & Jorgensen 2001 (10.1021/jp004071w,
perfluoroalkanes), which the class `ff_note` mentions by name but doesn't cite in the DOI field.
The class's other two citations (Afzal2021 `10.1021/acsapm.0c00524`, Hayashi2022/RadonPy
`10.1038/s41524-022-00906-4`) are both general cross-polymer high-throughput MD-informatics tools
(OPLS3e and GAFF2 respectively) — useful for corroborating system-size/cooling-rate protocol
ranges in general, but neither is a PVDF-specific or OPLS-AA-specific validation. Afzal2021's ACS
and ChemRxiv full text were both 403-blocked this run, so its specific halogen-class R²=0.87/
MAE=20.8K claim (quoted in the class `ff_note`) could not be independently re-verified — this is
the second class (after [[feedback_panh_ff_citation_mismatch]] PANH) where Afzal2021 shows up as
an unverifiable/mismatched citation. Worth treating Afzal2021 citations generally with extra
scrutiny across classes.

**Why:** a fabricated or mismatched DOI is worse than none — nothing downstream should treat
`ff_justification_doi` as validating the FF choice when the actual paper title/abstract doesn't
support that specific claim.

**How to apply:** when grounding PHAL (or auditing its rules entry), flag the Afzal2021
FF-family claim as `verified: false` in the literature_grounding.json output, cite Watkins2001 as
the real OPLS-AA-lineage source, and do not silently treat Byutner2000/Hayashi2022 as OPLS-AA
validations even though they're legitimately useful for density-target and general-protocol
grounding respectively. Per the worker's guard rail, do NOT edit the existing PHAL class entry —
only note the mismatch in the grounding JSON's `notes`/`dominant_uncertainty`.
