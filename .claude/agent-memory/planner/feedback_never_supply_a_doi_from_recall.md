---
name: never-supply-a-doi-from-recall
description: A source_doi must be copied from a file read this session or a verified grounding entry — never reconstructed from memory of a paper's identity
metadata:
  type: feedback
---

Never write a `source_doi` you did not copy from something you read this session (`polymer_rules.json`, `decision_policy.json`, a `verified: true` grounding source). On PLA1 I wrote `10.1016/j.commatsci.2019.03.050` for the Wu 2019 Murnaghan citation in D-07; `decision_policy.json` names "Wu (2019) Comput. Mater. Sci." with **no DOI**, so that identifier came from recall and was unresolvable in-session. Caught before handoff; the fix is to drop the `source_doi` key and keep `citation` with an in-repo pointer.

**Why:** `forcefield`, `electrostatics` and `property_method` are `evidence_required: true`, so `source_doi` is exactly the field a Critic checks — a plausible-looking wrong DOI is worse than an honest `citation`, and the repo already carries a 404-DOI incident ([[pdie-reasoned-plan]], Sharma2016). `decision_policy.json` accepts `claim + citation`; a DOI is not required.

**How to apply:**
- Naming the paper is fine ("Wu 2019 Comput. Mater. Sci., named in decision_policy.json:policies.property_method.rationale"). Numbering it is not.
- When the in-repo source deliberately carries no DOI, say so in the citation string so a Critic doesn't read the absence as an omission.
- Same rule for any other identifier you cannot re-read: file:line pointers are cheap and verifiable — prefer them.

Related: [[feedback-dont-assert-prior-run-results-unchecked]], [[plan-edit-hygiene]].
