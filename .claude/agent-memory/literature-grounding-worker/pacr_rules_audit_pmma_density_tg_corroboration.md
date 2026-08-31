---
name: pacr-rules-audit-pmma-density-tg-corroboration
description: PACR_rules_audit (2026-08-26) re-audit of polymer_rules.json PACR defaults found full agreement, plus a new corroborating density/Tg/electrostatics source for atactic PMMA
metadata:
  type: project
---

For the PACR_rules_audit run (class-default re-audit, not per-run planning), grounding confirmed
`polymer_rules.json`'s current PACR defaults are still literature-supported -- no override
indicated:

- **New source**: Trzeciak/Materials 2019, 10.3390/ma12203315 ("MD Study of Swelling of PMMA in
  Supercritical CO2") -- OPLS-AA, particle-mesh Ewald electrostatics, bulk PMMA density
  1161+/-2 kg/m3 at 333K matching its own cited exp target 1160 kg/m3; simulated Tg 417K vs its
  own cited exp range 363-387K (rate-artifact-inflated, same pattern as
  [[pmma-isotactic-tg-and-cooling-rate]]). This independently corroborates both the density and
  Tg (378K class default sits inside the 363-387K band) fields with a previously-unused DOI.
- **PCFF-vs-density-deficit tension flagged as dominant_uncertainty**: the commatsci 2025 review
  (10.1016/j.commatsci.2025.113861, already in the evidence store) reports Class II/PCFF PMMA
  density error <2%, but this codebase's own internal PACR campaign runs previously measured a
  PCFF PMMA density deficit of roughly -6% (see main MEMORY.md's PACR-adjacent verification
  notes). Literature and internal-run evidence agree on PCFF>GAFF qualitatively but disagree
  sharply in magnitude -- worth surfacing explicitly rather than silently picking one.
- **CTE (alpha_glass/alpha_melt) remains ungrounded** for atactic all-atom PMMA -- the one
  candidate found (10.1016/j.eurpolymj.2017.03.056, isotactic united-atom model) was DOI-verified
  but full-text-inaccessible (403) and chemistry-mismatched (isotactic UA vs this run's atactic
  all-atom target), so it was recorded `verified: false` and excluded from backing a value.
  `polymer_rules.json`'s experimental-equation-derived alpha values remain the best fallback.

See [[pmma-atactic-vs-isotactic-smiles-disambiguation]] and
[[pmma-isotactic-tg-and-cooling-rate]] for the underlying tacticity-Tg distinction this audit
reused.
