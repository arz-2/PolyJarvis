---
name: peg-rubbery-energy-drift
description: PEG3 (POXI, rubbery at 300K): energy drift 1.01% triggers EXTEND despite structural convergence
metadata:
  type: feedback
---

**Rubbery carve-out applies to reptation metrics only; energy drift is hard gate for all regimes.**

Why: PEG3 (DP=100, 300 K) showed density convergence (block-SEM 0.043%, homogeneity CV 21.3%), zero chain-spread (Rg CV 19.8%), good Gaussian MSID (1.098), but energy drift 1.01% (p=0.0001) failed the hard gate. The C(t) stall (3.7e9 ps τ_relax, 0% decay) and MSD kinetic trap (α=0.343) are expected for a glassy system but PEG at 300K is actually rubbery — those warnings are ADVISORY per regime carve-out. Energy drift, however, is thermodynamically significant and requires extension.

How to apply: For rubbery polymers, C(t), MSD, and Rg metrics remain ADVISORY. Energy convergence (drift <1%, SEM <1%) is a HARD GATE that applies equally to glassy and rubbery. EXTEND on energy drift even when structural metrics pass. Do NOT gate rubbery systems on C(t) decay or MSD displacement alone.
