---
name: pmma-isotactic-tg-and-cooling-rate
description: Isotactic PMMA literature Tg target (320-333K) diverges from class-default atactic (378K); verified MD Tg-sweep studies for PMMA all use ~1 K/ns cooling
metadata:
  type: project
---

For i-PMMA1 run (isotactic PMMA, PACR class, SMILES `*[C@@](C)(C(=O)OC)C*`), literature grounding
(2026-08-23) found:

- **Tacticity-resolved Tg targets differ sharply from the class default.** `polymer_rules.json`'s
  PACR.experimental_tg_K.PMMA = 378 K is the ATACTIC (commercial) value. Verified MD papers that
  resolve tacticity cite isotactic PMMA calorimetric Tg = 320 K (Macromolecules 2021,
  10.1021/acs.macromol.1c01341) to ~333 K (Soldera 2005, 10.1016/j.compositesa.2004.10.019);
  syndiotactic ~391 K. A run built with isotactic stereochemistry should be graded against the
  320-333 K band, not the 378 K class default.
- **All verified PMMA Tg-sweep MD studies use ~1 K/ns cooling**, not the 25-100 K/ns range in this
  class's `tg_rates_K_per_ns`. Three independent verified sources converge on this (Macromolecules
  2018 10.1021/acs.macromol.8b01160 stereoregular PMMA/graphene; Macromolecules 2021
  10.1021/acs.macromol.1c01341 tacticity study; Polymer 2022 10.1016/j.polymer.2022.125044,
  OPLS-AA, non-tacticity-resolved). Fast class-default rates should be expected to produce a
  rate-artifact-inflated Tg relative to any of these literature targets, isotactic or atactic.
- **PCFF vs OPLS-AA reconfirmed**: OPLS-AA PMMA Tg simulation (10.1016/j.polymer.2022.125044) gave
  481 K vs its own cited exp target 383 K (+25.6% error) — corroborates the existing
  NkepsuMbitou2025 (10.1016/j.commatsci.2025.113861) PCFF-preference finding already in
  `docs/ff_selection_literature.json` and `polymer_rules.json`.
- **No verified MD-derived numeric CTE (alpha_glass/alpha_melt)** for PMMA was found in this pass;
  `polymer_rules.json`'s existing alpha values are Mark2007 experimental-equation-derived, not
  MD-derived — still the best available fallback.
- **Electrostatics**: no PMMA-exact statement of PPPM/lj_cut found accessible (Soldera 2005 and the
  2018/2021 stereoregular Macromolecules papers paywalled beyond snippets). Recommendation (pppm)
  rests on ester-carbonyl-dipole chemistry argument + a general-practice confirmation from a
  315-polymer high-throughput MD dataset (Afzal 2021, 10.1021/acsapm.0c00524, uses PME/PPPM), not a
  PMMA-specific claim — kept at medium confidence, not high.

See [[docs-ff-selection-literature-workflow]] for the check-first-then-search procedure this came
from.
