---
name: trappe-result-block
description: PHYC/PDIE use trappe-ua; RESULT lammps_flags need use_trappe:true
metadata:
  type: project
  ingested_at: 2026-06-22
---

PHYC (polyhydrocarbons: PE/PP/PIB) and PDIE (polydienes: PBD/PI) route to the
`trappe-ua` field in the EMC server. The returned `lammps_flags` dict is
`{"use_pcff": false, "use_opls": false, "use_trappe": true}`.

**Why:** TraPPE-UA is a united-atom field — distinct from the PCFF and OPLS-AA
all-atom paths. The builder RESULT block template only enumerates use_pcff /
use_opls, so use_trappe must be added explicitly for these two classes.

**How to apply:** For PHYC/PDIE builds, pass `polymer_class` only (no field arg)
and report `lammps_flags` exactly as EMC returns it including `use_trappe`.
ff=TraPPE-UA, charges=gasteiger (embedded), electrostatics=lj_cut.
See [[emc-output-naming]].
