---
name: psil-si-ff-gap
description: PSIL (polysiloxane/PDMS) cannot be built. EMC now ACCEPTS PSIL (routes to opls/2024/opls-aa) but fails at FieldsApply — typing rules cover only tetraalkylsilane, not the siloxane Si-O backbone. RadonPy GAFF2 also has no Si.
metadata:
  type: project
ingested_at: 2026-06-05
---

PSIL (Polysiloxane, class_id 17, e.g. PDMS `*[Si](C)(C)O*`) currently CANNOT be built into a LAMMPS .data file by either Stage-1 builder. The wall has moved DEEPER over time — see the EMC section below; the old "rejected at API allowlist" claim is now STALE.

**EMC path (current state, verified 2026-06-04 evening):**
- `submit_emc_cell_job(polymer_class="PSIL")` is now **ACCEPTED** at the API level and routes to `field = "opls/2024/opls-aa"` (the allowlist gap recorded earlier this same day was fixed). It no longer returns "Unsupported polymer_class".
- The job then **FAILS during EMC execution** (job adec9653, exit 255) inside `core/fields.c:433 FieldsApply: Missing rules. Program aborted.`, with:
  `Warning: no rule found for {group, site} = {repeat, 0}.`
  `Warning: no rule found for {group, site} = {repeat, 9}.`
  Sites 0 and 9 are the two backbone connection atoms (the Si end and the siloxane bridging-O end).
- **Root cause (definitive, from reading the field files):** `/home/arz2/emc/field/opls/2024/opls-aa.prm` DOES contain `si4` (Si in tetraalkylsilane R4Si) plus `o2-si4` bond/angle params and `si4-o2-si4` angle (145 deg) — so PARAMETERS exist. BUT typing happens before params are applied, and `opls-aa.define` / `opls-aa.top` contain only four `si4` typing rules, all requiring a C/H-only coordination sphere:
  `[Si](~C)(C)(C)(C)`, `[Si](~C)(C)(C)(H)`, `[Si](~C)(C)(H)(H)`, `[Si](~C)(H)(H)(H)`.
  PDMS silicon is `[Si](O)(O)(C)(C)` — bonded to two backbone oxygens — and matches NONE of these rules. There is zero typing coverage for a siloxane Si (or a bridging O bonded to two Si). So `si4` can never be assigned to a PDMS backbone Si.
- **SMILES reordering does NOT help** (`*[Si](C)(C)O*` vs `*O[Si](C)(C)*`): the Si is bonded to two oxygens regardless of where `*` sits, so no rule matches. The `o2-si4` params in the .prm are a red herring — they're unreachable without a typing rule. This is a backbone-wide typing gap (Si AND bridging O), not a one-rule tweak.

**RadonPy / GAFF2 path:** still dead. `ff.ff_assign(mol)` returns `False`; RadonPy's `GAFF2.assign_atypes_atom` has NO silicon branch and GAFF2 tables have no `si`/`osi` keys. Only `dreiding.py` references Si. Do not pursue as a fallback — PSIL routes to EMC-OPLS-AA only (RadonPy Path B is PURA-only) and there's no field-override argument anyway.

**Why:** No force field shipped in the installed toolchain can TYPE the Si-O-Si siloxane backbone, even though OPLS-AA carries the siloxane bonded/nonbonded parameters.
**How to apply:** Do NOT attempt PSIL/PDMS builds expecting success. The EMC job will be accepted (don't be fooled by the green API response) and then fail at FieldsApply. Return a failure RESULT naming the FieldsApply typing gap. A real fix requires adding siloxane typing rules (`[Si](~O)...` and the bridging-O `O(~Si)(Si)`) to `opls-aa.define` and regenerating the .top — force-field development, out of Stage-1 scope. Recommend orchestrator set PSIL `builder_status: unsupported` in `guides/polymer_rules.json` until then.

**polymer_rules.json is misleading here:** its PSIL `ff_note` claims "GAFF2 has si/os atom types for organosilicone" and `preferred_ff: GAFF2` — FALSE for the installed RadonPy. Both `preferred_builder` and `preferred_ff` for PSIL are untrustworthy. The mcp-emc-server instructions also claim "opls-aa si4/o2 params for PDMS" — the PARAMS are there but the TYPING is not, so that claim is effectively false for building PDMS.
