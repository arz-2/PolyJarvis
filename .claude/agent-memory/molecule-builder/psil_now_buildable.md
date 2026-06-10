---
name: psil-now-buildable
description: PSIL (polysiloxane/PDMS) is now BUILDABLE via EMC opls/2024/opls-aa after the 2026-06-05 siloxane typing patch. Supersedes the old "unsupported" wall. Build PDMS normally; do not return a failure RESULT.
metadata:
  type: project
ingested_at: 2026-06-10
---

PSIL (Polysiloxane, class_id 17, e.g. PDMS `*[Si](C)(C)O*`) **can now be built** into a LAMMPS .data file via EMC. This SUPERSEDES the earlier `psil_si_ff_gap.md` memory (deleted) which declared PSIL unsupported — that wall (verified 2026-06-04) was the missing siloxane typing rules, and it was patched 2026-06-05.

**The fix (present on disk in `/home/arz2/emc/field/opls/2024/opls-aa.define`):**
- Line 4892: `si4  [Si](~O)(O)(C)(C)` — PDMS internal Si (two O, two C). This is the exact rule the old memory said was absent.
- Line 4893: `si4  [Si](~O)(C)(C)(H)` — terminal Si.
- Line 2013: `o2  O(~[Si])([Si])` — bridging siloxane oxygen.
- Lines 1231/1233: `o2h O([Si])(H)` and `h1o H(O([Si]))` — silanol cap typing.
The `o2-si4` bond/angle/torsion params were already in `opls-aa.prm`; only the typing rules + o2-si4/o2h-si4 charge increments were the gap, and those are now added.

**Verified build (job f4c83340, 2026-06-06):** smiles `*[Si](C)(C)O*`, dp=80, nchain=10, ntotal=8000, density_initial=0.49 → 8020 atoms, 7 atom types {c4, h1, h1o, h1si, o2, o2h, si4}, field opls/2024/opls-aa. Completed in ~3.5 min, no FieldsApply error. Earlier dp=20 test (job 041f41a1) → 3030 atoms also succeeded.

**Why:** Force-field development added the siloxane typing coverage that was missing from the shipped OPLS-AA toolchain.
**How to apply:** Build PSIL/PDMS normally via `submit_emc_cell_job(polymer_class="PSIL")` → routes to opls/2024/opls-aa → `lammps_flags={use_pcff:false, use_opls:true}`. Charges are embedded as BCIs (si4_internal=+0.94, si4_terminal=+0.82, o2=-0.44, o2h=-0.60); no QM charge step. EMC build seed defaults to -1 and is NOT persisted as a resolved integer — report it as auto-seeded. RadonPy/GAFF2 still has no Si branch, so EMC-OPLS-AA remains the only path. `polymer_rules.json` PSIL `builder_status` is "supported" — trust it.
