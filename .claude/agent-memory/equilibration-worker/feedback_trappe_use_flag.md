---
name: feedback_trappe_use_flag
description: PHYC/PDIE/PSTR polymer classes need use_trappe=True in generate_equilibration_workflow; this flag is absent from lammps_flags and must be inferred from polymer_class
metadata:
  type: feedback
ingested_at: 2026-06-05
---

The orchestrator's `lammps_flags` dict only carries `use_pcff` and `use_opls`. There is no `use_trappe` key. However, `generate_equilibration_workflow` has a dedicated `use_trappe` parameter that switches all templates to `pair_style lj/cut 14.0` (no kspace), `dihedral_style multi/harmonic`, and disables SHAKE.

**Why:** Without `use_trappe=True`, the generator defaults to GAFF2-style `lj/charmm/coul/long` + PPPM + fourier dihedrals — wrong physics for TraPPE-UA united-atom systems, and it fails silently.

**How to apply:** When `polymer_class` is PHYC, PDIE, or PSTR (regardless of what `lammps_flags` contains), always set `use_trappe=True` in `generate_equilibration_workflow`. Also set `lj_cutoff=14.0` in `validate_data_file` (TraPPE default) instead of the 12.0 GAFF2 default.
