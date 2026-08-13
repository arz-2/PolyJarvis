---
name: sharma2016-doi-typo-polymer-rules
description: guides/polymer_rules.json primary_sources.Sharma2016 has a wrong DOI (404s); correct DOI found and verified
metadata:
  type: feedback
---

`guides/polymer_rules.json` `_metadata.primary_sources` entry id `Sharma2016` (cited by the PDIE
class for cis/trans-PBD and PI Tg validation) lists `doi: "10.1021/jp510632u"`, which 404s on
doi.org. The correct DOI, verified by resolving to https://pubs.acs.org/doi/10.1021/acs.jpcb.5b10789
(title/authors/journal/year all match "Sharma, Roy, Karimi-Varzaneh, Validation of Force Fields of
Rubber through Glass-Transition Temperature Calculation by Microsecond Atomic-Scale Molecular
Dynamics Simulation, J. Phys. Chem. B 2016, 120, 1367–1379"), is `10.1021/acs.jpcb.5b10789`.

**Why:** step 2 of the literature-grounding workflow requires verifying every DOI before citing it
— this one silently fails. I did not fix it in `polymer_rules.json` because the worker instructions
only permit *adding* a brand-new class entry (step 7), never editing an existing one's fields.

**How to apply:** next time a class's `primary_sources` entry is cited, resolve its DOI first. If
`Sharma2016` (or any entry) 404s, flag it here again and let a human/orchestrator patch
`polymer_rules.json` directly — this worker cannot safely self-correct that file.
