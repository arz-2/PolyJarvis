---
name: pcff_class2_styles
description: PCFF Class II force field requires explicit class2 styles in LAMMPS .in
metadata:
  type: reference
---

**PCFF (Class II) FF styles** for POXI and other PCFF classes:

Correct:
```
pair_style lj/class2/coul/long 9.5 9.5
bond_style class2
angle_style class2
dihedral_style class2
improper_style class2
special_bonds lj/coul 0 0 1
```

Wrong (harmonic, amber, charmm, fourier, cvff — causes simulation crashes or wrong energies):
```
bond_style harmonic
angle_style harmonic
dihedral_style fourier   # or charmm, cvff, etc.
```

**How to verify:** After script generation, grep the .in file for `bond_style`, `angle_style`, `dihedral_style`, `improper_style`, `pair_style`. All must say `class2`.

The template engine respects lammps_flags `use_pcff=true` to select class2 styles automatically.
