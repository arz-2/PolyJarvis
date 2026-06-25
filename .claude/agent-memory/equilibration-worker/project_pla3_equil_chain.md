---
name: pla3-equil-chain
description: PLA3 glassy PEST, PCFF, kokkos, GPU 1, 9-stage chain 905e9409, 2026-06-24
metadata:
  type: project
  ingested_at: 2026-06-25
---

PLA3 equilibration chain submitted 2026-06-24.

- Polymer: Polylactic Acid (PLA), class PEST
- FF: PCFF (use_pcff=True)
- Engine: kokkos, GPU 1, MPI=1
- n_atoms: 4520
- T_equil_K: 620, T_anneal_high_K: 700, P: 1 atm
- chain_id: 905e9409
- n_stages: 9 (glassy path: npt_cool300 + npt_prod300 appended)
- work_dir: data/PLA3/lammps/equil
- npt_prod300_data: data/PLA3/lammps/equil/npt_prod300/npt_prod300_out.data
- sentinel: /tmp/polyjarvis/sentinels/done_905e9409.json

**Why:** Tracking for session recovery and cross-run context.
**How to apply:** If PLA3 run needs recovery, start from chain_id 905e9409 and check sentinel above.
