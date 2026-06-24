---
name: psfo-routing
description: PSFO (polysulfone) routes EMC/PCFF; classify co-occurs with POXI+PPNL but PSFO wins; charge_method none (EMC assigns)
metadata:
  type: project
---

PSFO (polysulfone, e.g. PSU/Udel, PES) builds via EMC with PCFF (Class II). `classify_polymer` reports class_id=20, preferred_builder=emc, preferred_ff=pcff, ff_confidence=medium.

**Why:** PCFF/EMC handles the sulfone (S(=O)(=O)) + aromatic ether backbone in one step — EMC assigns all FF params and charges, so charge_method=none, electrostatics=pppm. classify reports co_occurring_groups POXI (ether O) + PPNL (phenylene-vinylene SMARTS partial-match on the aromatic rings), but PSFO is the correct primary class — the co-occurrence is expected, not a misclassification.

**How to apply:** For PSFO, submit_emc_cell_job(polymer_class="PSFO") — field auto-selected as pcff, do not override. RESULT lammps_flags = use_pcff:true, use_opls:false. Reference build: PSU2, BPA-polysulfone SMILES, dp=20 nchains=10 density_initial=0.62 → 10820 atoms, cubic box ~61.9 A, 8 atom types. ff_confidence=medium because no class-specific PCFF MD validation paper exists yet (Sun1994 CFF93 origin). See [[emc-output-naming]], [[emc-seed-not-persisted]].
