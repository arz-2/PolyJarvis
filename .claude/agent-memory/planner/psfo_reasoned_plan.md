---
name: psfo-reasoned-plan
description: How to build a PSFO (polysulfones — PSU/PES/PPSU) reasoned run_plan — confidence=medium, in-table temps, PCFF/EMC, glassy K, multi-member exp Tg
metadata:
  type: feedback
  ingested_at: 2026-06-25
---

PSFO (Polysulfones) is confidence=medium and IS in polymer_rules.json with class-specific temperatures (T_equil=700, anneal=780/8cyc, Tg sweep 250-750 K @ 20 K step, rates [25,50,100] K/ns, dp_typical=25, nchain=8). Build a **reasoned** plan (not deterministic).

**Why:** medium confidence forces reasoned mode (Critic escalates deterministic on a non-high class). PSFO is a **multi-member** class — exp Tg is a dict {PSU:463, PES:493, PPSU:493} — so disambiguate by SMILES. See [[multimember-class-exp-tg-resolution]].

**How to apply:**
- **Member resolution by SMILES:** isopropylidene bridge `C(C)(C)` between aryl ether + aryl sulfone => **PSU (Udel, bisphenol-A polysulfone)**, exp Tg=463 K, density~1.24-1.25, K_T=4.0-5.5 GPa. Para-only ether-sulfone (no isopropylidene) => PES (493 K). Pin the resolved member's targets in D-04 evidence (`value_K`) + assumptions; drive is_glassy off the pinned exp Tg.
- **Skip** `estimate_tg_group_contribution.py` — in-table class-specific temps; only off-table/confidence=low use it. Leave scaffold global_defaults unchanged.
- **Dominant uncertainty = `ff_transferability`**, `reduction_probe: literature_anchor`. No class-specific PCFF MD Tg/density paper for polysulfones; PCFF Class II covers aryl-SO2-aryl + aryl ether by analogy (PC Tg 417 vs exp 422). MD Tg for PSU expected ~540-580 K (overprediction) per polymer_rules notes — that's why the sweep tops out at 750 K.
- **D-01 FF = pcff** via EMC. Reject GAFF2_mod (Tg err >45% PMMA) and OPLS-AA (its sulfone charges ~+1.3/-0.55 differ from PCFF native bond-increment S~+0.08/O~-0.11). Cite ja00086a030 + Hayashi2022/Afzal2021.
- **D-02 charges = none** (PCFF bond-increment). Caveat to record: a charge of exactly 0.0000 on S or sulfone O means a MISSING frc increment, not a small value — verify so2/o_2s atom types in EMC PCFF output before run.
- **D-03 = pppm REQUIRED** — backbone heteroatoms (sulfone S + 2 O, ether O) carry charges; lj/cut only for apolar UA.
- **D-07 = glassy** (PSU exp Tg 463 >> 300): Murnaghan NPT compression at 300 K primary, deform fallback, Born+NVT removed. Exp K_T 4.0-5.5 GPa (Zoller 1978 via Mark 2007 Table 7.6). DP=25 ~1 M_e: adequate for Tg, short of entanglement for K → flag K offset.
- **D-08 hardware:** family=pcff. Cell ≈ dp25 × nchain8 × **57 all-atom/monomer** (PSU repeat, incl. ether-O caps) ≈ **11,400 atoms** (>10k). Still adopt by_forcefield.pcff default (kokkos, mpi=1, gpu_per_run=1): directional_probe HINT-only (values_are_benchmarked=false, host A800/RTX6000 not clean live host, 11.4k is ~3.8x the 3020-atom pcff bench cell, outside [0.5x,2x]); no multi-GPU pin (recommended_by_ff.pcff.gpu=1, no benchmark support for >10k). Keep decided_params hardware-free (choice = default → stay on policy path), set D-08 confidence=low + planned `hardware_benchmark` probe (uncertainty `hardware_optimum`).
- **D-06 ladder [25,50,100]** clears steps-per-T floor at dt=1fs/step=20K (800/400/200 ps). Sweep 250-750 K brackets exp 463 K AND expected MD 540-580 K — set `t_range_brackets_exp_tg: true`.
