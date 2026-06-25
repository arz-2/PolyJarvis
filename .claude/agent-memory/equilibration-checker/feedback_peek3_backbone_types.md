---
name: peek3_backbone_types_error
description: PEEK3 initial backbone_types misidentification; hydrogens vs heavy atoms
metadata:
  type: feedback
---

## Initial error

Passed `backbone_types=[3,4]` to `check_equilibration_comprehensive`. These are **hydrogens** (mass 1.008), not backbone atoms. Tool was computing R_ee, P2, C(t), MSD on H–H pseudo-structure (degenerate, no H–H bonds).

## Root cause

Confused "aromatic atoms" with "aromatic backbone atoms." Read Pair Coeffs epsilon/sigma instead of Masses section:
- Type 3: σ=2.995 Å, mass=1.008 → hc (aromatic H), NOT aromatic C
- Type 4: σ=1.098 Å, mass=1.008 → polar H (O–H), NOT aromatic C

## Fix

Read `Masses` section first. For PEEK:
- Types 1, 2: mass 12.01 → **Carbons** (aromatic backbone)
- Types 3, 4: mass 1.008 → Hydrogens ✗
- Types 5, 6, 7: mass 16.00 → Oxygens (ether/ketone in chain)

Correct backbone: `[1, 2, 5]` (aromatic C + ether O) or `[1, 2]` (C-only).

## Why it matters

Non-binding P2 gate on glassy PKTN, but degenerate-backbone P2 can spuriously pass/fail → wrong verdict path (PASS vs EXTEND). R_ee is a required field; garbage backbone → garbage R_ee output.

## How to apply

Always check `Masses` section before `Pair Coeffs` when selecting backbone_types for aromatic polymers. Never rely on visual inspection of coefficient values.
