# FF Validation Status — Phase 1 Audit
_Last updated: 2026-06-11_

This file documents conflicts, mismatches, and gaps found during the Phase 1 literature review.
It feeds the Phase 2 web search and the subsequent polymer_rules.json update.

---

## Confirmed Conflicts (polymer_rules.json vs actual paper content)

### 1. PACR — PCFF for PMMA: CONFIRMED CORRECT (conflict resolved 2026-06-11)
- **Current state**: `ff_justification_doi = NkepsuMbitou2025`, `confidence = high`
- **What NkepsuMbitou 2025 actually shows (Figure 6, Section 5.2)**:
  - PMMA raw Tg ≈ 450 K at 10 K/ns cooling rate (expected — fast cooling raises apparent Tg)
  - WLF-corrected PCFF PMMA Tg: within 10% of experimental ~378 K ✓
  - Class II FFs (PCFF, IFF) are most robust across 5 configurations (lowest variance)
  - Paper conclusion: "all Class II FFs in excellent agreement within 10% for PMMA"
  - PIB: GAFF is the worst performer (>45% error, underestimates to ~120 K); PCFF within 10% ✓
- **Resolution**: Phase 1 Explore agent confused PMMA vs PIB data in Figure 6. The raw ~450 K
  value belongs to PMMA (not PIB), and WLF-corrected Class II FFs agree within 10% for both.
- **No conflict**: confidence=high for PACR with PCFF is fully justified.
- **PHYC note correction**: PCFF is NOT a poor choice for PIB — it gives ~10% error.
  TraPPE-UA choice for PHYC is justified by Ramos 2015 direct PE validation + UA computational
  efficiency for pure C/H backbones, not by "PCFF fails for PIB."

### 2. PSTR — Wick 2000 cited as TraPPE-UA PS Tg validation: wrong paper type
- **Current state**: `ff_justification_doi = 10.1021/jp001044x` (Wick 2000 TraPPE-UA 4, alkenes
  and alkylbenzenes), `confidence = high`
- **What Wick 2000 actually is**: FF parameterization paper for TraPPE-UA alkenes and
  alkylbenzenes. Validates VLE and conformational properties, **not Tg**.
- **Spyriouni 2007** (in literature folder): also invalid — uses custom IBI CG model, not
  TraPPE-UA; does not measure Tg at all. Only validates density, Rg, entanglements.
- **Conflict**: No paper in our literature folder validates TraPPE-UA PS Tg against experiment.
  confidence=high is unsubstantiated for Tg prediction.
- **Action**: Find a paper that reports PS Tg using TraPPE-UA specifically.

### 3. Tang & Okazaki 2022 — valid for PCBN only, not PACR
- **What the paper does**: Uses PCFF for PC → Tg = 417 K vs exp 422 K (−1.2%) ✓
  Uses **OPLS-AA** for PMMA → Tg = 481 K vs exp 383 K (+98 K, FF inadequate for PMMA).
- **Conflict**: If Tang 2022 is cited or intended as PMMA validation, it uses the wrong FF
  (OPLS-AA, not PCFF) and shows very poor agreement.
- **Action**: Credit Tang 2022 to PCBN only. PACR needs a separate PCFF PMMA paper.

### 4. PDIE — Ramos 2015 cited as ff_justification_doi: wrong class
- **Current state**: `ff_justification_doi = 10.1021/acs.macromol.5b00823` (Ramos 2015), same as PHYC
- **What Ramos 2015 covers**: Polyethylene only — linear C₁₉₂ chains, TraPPE-UA alkane types
  (CH₂/CH₃). Does not cover diene backbone (CH₂=CH– or –CH=CH– UA types) or PBD/PI.
- **Conflict**: PDIE (polydienes: PBD, PI) uses TraPPE-UA diene atom types from Wick 2000 TraPPE-4.
  Ramos 2015 validates linear alkane types, not diene types. The Tg extrapolation to PBD/PI is
  an extension without direct validation.
- **Action**: Find a paper validating TraPPE-UA PBD or PI Tg.

### 5. Sun 1994 (10.1021/ja00086a030) — FF origin paper, not Tg validation
- **Used as ff_justification_doi for**: PAMD, PKTN, PSFO, PIMD, PCBN (PCBN now upgraded to
  Tang 2022 for Tg; Sun 1994 remains as FF origin).
- **What Sun 1994 is**: Original CFF93/PCFF force field derivation paper. Validates FF on small
  organic molecules and model compounds; does not report polymer Tg simulations.
- **Conflict**: Citing it as Tg justification implies it validates polymer Tg with PCFF; it does not.
- **Action**: Keep Sun 1994 as `ff_origin_doi` (new field) or remove from `ff_justification_doi`.
  Replace with a class-specific Tg paper for PAMD, PKTN, PSFO, PIMD.

### 6. Afzal 2021 (10.1021/acsapm.0c00524) — OPLS3e paper, cited for PCFF classes
- **Used as ff_justification_doi for**: PVNL, PSUL, PURT, PIMN, PPNL, PANH, PPHS, PURA, PDIE,
  PSIL, PHAL, POXI, PEST, PACR (alongside or replacing other citations).
- **What Afzal 2021 is**: High-throughput MD study of 315 polymers using **OPLS3e**, not PCFF.
  Provides experimental Tg targets; does NOT validate PCFF accuracy for any class.
- **Conflict**: For PCFF-routed classes, citing Afzal 2021 as ff_justification implies MD Tg
  was validated with PCFF; it was not.
- **Action**: Afzal 2021 is valid only as an experimental Tg reference. For classes where it is
  the sole citation, it cannot stand as FF validation. Needs replacement with actual PCFF papers.

---

## Papers Requiring More Precise Data

### 1. NkepsuMbitou 2025 — PCFF PMMA error (PACR)
- Agent read Tg values from figures (approximate); reported PCFF PMMA Tg ≈ 450 K vs exp ≈ 380 K.
- If true: ~18% overestimate — beyond our 10% threshold for confidence=high.
- But figure-reading has ±20 K uncertainty. **Need tabulated values** from the paper.
- If precise value is <10% error, confidence=high stands; if >10%, downgrade to medium.

### 2. Wen 2020 — PIMD polyimide PCFF Tg
- Cited in PIMD `ff_note` and `notes` fields in polymer_rules.json as validating PCFF for
  PMDA-ODA (Kapton) Tg range 451–691 K.
- **Not in literature folder**; not in `_metadata.citations`.
- Full citation unknown — could be: Wen, X. et al. (2020), journal unknown, polyimide PCFF MD.
- **Action**: Find Wen 2020, download if available, add to literature folder and citations.

---

## Neutral Findings (no conflict, useful context)

### NkepsuMbitou 2025 — PCFF failure for PIB validates PHYC TraPPE-UA choice
- PCFF overestimates PIB Tg by ~150–200 K.
- PHYC uses TraPPE-UA (not PCFF) — this paper strongly supports that choice.
- Add to PHYC `ff_note`: "NkepsuMbitou 2025 shows PCFF fails for PIB (+150-200 K); 
  TraPPE-UA (Ramos 2015) is the validated choice."

### Suter 2025 — PCFF epoxy partial credit for PIMN
- Validates PCFF for amine-cured epoxy thermosets (not linear PEI/Ultem).
- MAE 11–21 K across 6 epoxy systems.
- Partial indirect evidence that PCFF handles N–C–O interactions well; not a direct PIMN validation.

### Tang & Okazaki 2022 — confirmed strong PCFF PC validation for PCBN
- 417 K vs 422 K (−1.2%), 1 K/ns cooling, good agreement.
- Should be added to PCBN `_metadata.citations` and `ff_justification_doi` updated.

### Soldera 2006 — covers PE, PMMA, PMA, PS, PMS but wrong FFs
- COMPASS + AMBER/OPLS, not PCFF or TraPPE-UA.
- Could serve as "any MD Tg paper" credit for PSTR (PS) but not FF validation.
- PS at Γ₃ = 449–484 K; WLF-corrected converges to ~373 K (matches exp 373 K).

---

---

## Phase 2 Web Search Results (2026-06-11)

### Papers Found — Ready to Add

| Class | Paper | FF | MD Tg | Exp Tg | Error | Notes |
|-------|-------|----|-------|--------|-------|-------|
| **PIMD** | Wen et al. 2020, J. Polym. Sci. 58:1521, DOI:10.1002/pol.20200050 | PCFF | covers multiple PIs | ~633 K (PMDA-ODA) | ~40 K (density method) | Also the Wen2020 missing from _metadata |
| **PIMN** | Wen et al. 2020 (same paper) | PCFF | 525 K (Ultem/4,4'BPADA+MPD) | ~490 K | +35 K (+7%) | Ultem is 4,4'BPADA-MPD = Ultem 1000 |
| **PKTN** | PEEK catechol oligomer 2020, Polymers MDPI, DOI:10.3390/polym12051054 | COMPASS II | 424–429 K | 418 K | +6–11 K (+1–3%) | COMPASS II not PCFF exactly; Class II family |
| **PVNL** | Li et al. 2019, Chinese J. Polym. Sci. 37:834, DOI:10.1007/s10118-019-2249-5 | COMPASS | ~390 K | ~390 K (PVC/DOP) | ~0 | PVC blend; also find Sundaramoorthi 1999 (pure PVC PCFF) |
| **PVNL** | Sundaramoorthi & Bicerano 1999, Polymer 40(7) | PCFF | reported | reported | not available | Pure amorphous PVC, PCFF + DISCOVER; early validation |
| **PPNL** | Venkatanarayanan et al. 2016, Macromol. Theory Simul. 25:238, DOI:10.1002/mats.201600006 | PCFF | 416 ± 8 K (PPV) | ~416 K | ~0% | Direct PCFF PPV Tg validation; also covers polyacetylene |
| **PSIL** | Huang et al. 2024, J. Phys. Chem. B 128(50), DOI:10.1021/acs.jpcb.4c08471 | Multi-FF benchmark incl. OPLS-AA | ~148–183 K range (FF-dependent) | ~148 K | OPLS-AA: moderate; Class II best | Multi-FF benchmark; confirms OPLS-AA is usable for PDMS |
| **PPHS** | Tiwary et al. 2022, Polymers 14:1451, DOI:10.3390/polym14071451 | Not confirmed (COMPASS-based) | Fox eq. Tg | variable | — | Poly(ethoxy/phenoxy)phosphazene; "any MD Tg" standard |
| **PURT** | PCFF polyurethane 2026, Polymers 18:679, DOI:10.3390/polym18060679 | PCFF+COMPASS | cure-dependent | cure-dependent | — | Fast-cure TPU; cure–Tg relationship |
| **PDIE** | Sharma et al. 2016, J. Phys. Chem. B, DOI:10.1021/jp510632u | Multiple FFs (UA models) | PBD/PI Tg validated | ~181/200 K | "excellent agreement" | Confirms multiple UA FFs for PBD/PI; need full text to confirm if TraPPE-UA is one |

### Gaps Remaining After Phase 2

| Class | Status | Best available | Recommended action |
|-------|--------|---------------|-------------------|
| **PSTR** | No TraPPE-UA PS Tg paper found | Soldera 2006 (COMPASS+OPLS PS; in literature folder) OR Harmandaris 2002 (custom UA, not TraPPE-UA) | Lower confidence to medium; cite Soldera 2006 as "any MD Tg" evidence; note TraPPE-UA PS Tg gap |
| **PAMD** | No PCFF Nylon paper confirmed | Chantawansri 2015 (Polymer 81, DOI:10.1016/j.polymer.2015.09.069) — FF unconfirmed; Lukasheva 2017 uses AMBER99sb | Cite Chantawansri 2015 as "any MD Tg" (need to confirm FF); confidence stays medium |
| **PSFO** | No PCFF PSU paper found | ResearchGate reference to sub-transition MD study (PSU) — no full-text access | Confidence=medium; note PCFF PSU Tg validation missing |
| **PSUL** | No PCFF PPS paper found | Modified polyarylene sulfide 2024 (CJPS) — FF not confirmed as PCFF | Note gap; confidence=medium |
| **PURA** | CG model only (Omidi 2014 already noted) | No all-atom PCFF polyurea Tg found | Keep confidence=low; keep existing Omidi 2014 citation |
| **PANH** | No polyanhydride MD Tg found (PLGA CG is polyester, not pure anhydride) | — | Keep confidence=low |

### Open Conflict — NkepsuMbitou 2025 (PACR) — RESOLVED 2026-06-11
- Phase 1 agent misread Figure 6: confused PMMA (squares) and PIB (diamonds) in the bar chart.
- Actual paper (Figure 6 + Section 5.2 text):
  - PMMA: all Class II FFs within 10% WLF-corrected; PCFF raw ≈ 450 K → WLF-shifted ≈ 378 K
  - PIB: GAFF worst (>45% error, ~120 K); Class II FFs (PCFF, IFF) within 10%
- PCFF is the recommended FF for both PMMA and PIB by this paper. Conflict does not exist.
