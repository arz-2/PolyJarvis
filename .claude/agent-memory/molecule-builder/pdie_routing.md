---
name: pdie-routing
description: PDIE (PBD/PI) routes to EMC/TraPPE-UA, but EMC ignores SMILES cis/trans stereo markers — builds a ~50:50 mixture; verify by torsion geometry, never by atom type
metadata:
  type: project
---

PDIE → EMC + `trappe-ua`, charge none, `lj_cut`, `lammps_flags = {use_pcff:false, use_opls:false, use_trappe:true}`
(the third key is TraPPE's only downstream routing signal — don't drop it).

**EMC does not honor SMILES stereo markers for PDIE.** Built `*C/C=C\C*` (dp=100, nchain=20,
seed 482913) and got 47.9% cis / 52.1% trans, randomized per repeat unit (per-chain cis fraction
36–53%, no chain uniform). The `/` and `\` survive into `emc_build.esh` and `build.emc`, so the
markers reach EMC and are silently discarded at build.

**Why:** installed `~/emc/field/trappe/2014/` has a single stereo-agnostic alkene type `c3h`
("CH (SP2) 2-alkene"); a cis-PBD cell carries only 3 atom types (c3h, c4h2, c4h3). The C=C torsion
`dihedral_coeff 4  25.63496 0.99360 -25.63496 -0.99360 0` (c4h2,c3h,c3h,c4h2) is a symmetric
double well — E=0 at both 0° and 180°, ~25.6 kcal/mol barrier at 90°. So the FF locks in whatever
EMC's builder randomly picked, and MD will never fix it.

**How to apply:** for any PDIE request that names a specific isomer, never assert the microstructure
from atom-type names — they cannot discriminate. Compute the CH2–CH=CH–CH2 torsion from the built
`.data` (bond type 1 = C=C, r0 1.33 Å; |phi|<90 cis, >90 trans) and report the measured fraction.
If the request is isomer-specific, report the mixture as campaign-blocking: cis vs trans PBD Tg
differ by ~60 K. Fix requires a 3D cis template or a stereo-aware builder (RDKit/RadonPy), not a
different seed or dp.

`polymer_rules.json` PDIE `ff_justification` claims TraPPE-4 "defines cis/trans-CH=CH- UA types" and
that microstructure "must be encoded in SMILES" — both false for the installed field. See
[[pest_routing]] for the EMC-path field-routing pattern.
