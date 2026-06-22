---
name: pstr-reasoned-plan
description: PSTR (polystyrenic, e.g. PS/aPS) is confidence=medium -> reasoned plan; key judgment calls and exp anchors
metadata:
  type: project
  ingested_at: 2026-06-22
---

PSTR is confidence=medium in polymer_rules.json -> reasoned plan, NOT deterministic. It HAS class-specific temperatures, so skip group-contribution Tg estimation (that step is only for off-table/confidence=low).

**Why medium, not high:** No direct PCFF PS Tg validation paper exists. PCFF Class II is validated on PC (Tg 417 vs 422 K) and PMMA vinyl backbone (<10%), but PS aromatic-pendant vinyl is an analogy. This is the dominant uncertainty (`pcff_ps_tg_transferability`, reduction_probe=literature_anchor).

**How to apply (PS member specifics):**
- exp anchors for PS member: Tg=373 K (class default exp Tg key is 374 = P2VP; pin 373 for PS). RT density=1.05 g/cm3. K=3.5-5.5 GPa. Set these in decided_params (experimental_tg_K, experimental_density_gcm3) and the tg success_criteria `t_range_brackets_exp_tg`=373.
- Cell estimate: styrene monomer = C8H8 = 16 all-atom. DP40 x nchain10 x 16 = ~6,400 atoms -> <10k -> 1 GPU. Matches class note "6,400 atoms".
- FF was switched from TraPPE-UA -> PCFF on 2026-06-11 (UA omits ring charges/pi-dihedrals). Record TraPPE-UA as rejected alternative.
- charge_method=RESP (HF/6-31G*) for phenyl pi polarization; AM1-BCC fallback.
- K is screening-grade: DP=40 < DP@Me=160 (aPS Me=16,600). Use Born+NVT (glassy, rate-free) to avoid compounding the deform strain-rate inflation on top of sub-entanglement DP underestimate. Non-dominant uncertainty.

**Hardware:** pcff default {gpu, mpi4, gpu1} == directional_probe winner gpu1_mpi4. But values_are_benchmarked=false and ~6.4k cell is ~2.1x the 3020-atom probe cell (just outside [0.5,2]x), so keep by_forcefield default, set D-08 confidence=low, add hardware_optimum uncertainty w/ reduction_probe=hardware_benchmark. Choice==default -> leave decided_params hardware-free (keeps prompt byte-identical).
