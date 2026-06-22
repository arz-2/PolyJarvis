---
name: project_pe1_melt_npt_protocol
description: PE1 density re-run corrected equilibration protocol — melt branch required to fix +25% over-density failure
ingested_at: 2026-06-20
metadata:
  type: project
---

PE1 replicate 1 (2026-06-18): corrected protocol for density over-estimation (~1.19 vs exp 0.95 g/cm³).

**Fix:** pass `add_melt_npt=True, t_equil_K=550.0, melt_npt_steps=1000000, npt_prod_steps=5000000, use_trappe=True` to `generate_equilibration_workflow`. This triggers the 9-stage melt-branch chain (minimize → nvt_softheat → npt_compress → npt_pppm → npt_cool_melt → npt_melt → npt_cool → nvt_production → npt_production).

**Why:** Prior run used 7-stage chain without melt hold; cooling too fast from 620 K → 300 K trapped high-density metastable state. Melt-density hold at 550 K + slower cool (620→550→300) relaxes chain packing.

**How to apply:** Any PHYC (TraPPE-UA) polymer re-run with suspected over-densification: use add_melt_npt=True. Verify n_stages=9 in generate_equilibration_workflow return before submitting.

Seeds: EMC=1001, SEED_HOT=1002, SEED_COLD=1003 (replication study — fixed).
Chain submitted: chain_id=48517238, gpu_ids="0", mpi=1.
npt_prod_steps=5000000 (10 ns @ 2 fs).
