# Protocol Justification Table — Revision Polymers

Per-polymer protocol justification for the 9 revision systems. Used in R1M8 (Table 1 FF/charge rationale)
and as internal reference for R2 re-run decisions. All values sourced from `polymer_rules.json` unless noted.

---

## Summary table

| Polymer | Class | FF | T_equil_K | T_equil justification | t_equil_ns | t_equil justification | nchain × dp | Tg sweep window | dp vs Me | Protocol source |
|---------|-------|----|----------:|-----------------------|------------|----------------------|-------------|-----------------|----------|----------------|
| PE | PHYC | TraPPE-UA | 550 | Tm≈400 K; 550 K = Tm + 150 K (1.4×Tm in K) ✓ | 5 | τ_Rouse(dp=120) at 550 K ≈ 2–5 ns (Ramos2015); 5 ns >> τ_Rouse ✓ | 20 × 120 | 100–450 K | dp=120 >> dp@Me(PE)≈80 ✓ entanglement-converged K | Ramos2015; TraPPE-UA Ramos+Pastorino |
| aPS | PSTR | PCFF | 550 | Tg≈373 K; 550 K = Tg + 177 K ✓ | 5 | reasonable for 40-mer rigid backbone; no specific PS relaxation ref at dp=40 | 10 × 40 | 200–600 K | dp=40 << dp@Me(PS)≈160 ⚠ | Tang2022; NkepsuMbitou2025 |
| PMMA | PACR | PCFF | 550 | Tg≈378 K; 550 K = Tg + 172 K ✓ | 5 | reasonable for 40-mer; consistent with NkepsuMbitou2025 protocol | 10 × 40 | 150–600 K | dp=40 << dp@Me(PMMA)≈125 ⚠ | NkepsuMbitou2025; Klajmon2023 |
| PEG | POXI | PCFF | 500 | Tg≈206 K; Tm(PEO)≈340 K; 500 K = Tm + 160 K ✓ | 4 | flexible ether backbone; Wu2011 used 5 ns at 100-mer ✓; 4 ns adequate for dp=100 | 10 × 100 | 100–440 K | dp=100 > dp@Tg-convergence≈90 (Klajmon2023) ✓ | Klajmon2023; Wu2019 |
| PLA | PEST | PCFF | 620 | Tm≈430 K; 620 K = Tm + 190 K ✓ | 5 | reasonable for ester backbone; no PLA-specific τ_Rouse ref at dp=50 | 10 × 50 | 100–600 K | dp=50; Me(PLA) not benchmarked; screening compromise | Klajmon2023 |
| PVC | PVNL | PCFF | 530 | Tg≈354 K; 530 K = Tg + 176 K ✓ | 5 | reasonable for polar vinyl backbone; no PVC-specific MD relaxation ref | 10 × 60 | 150–550 K | dp=60 << dp@Me(PVC)≈160 ⚠ | no specific PVC MD paper; Webb2024 for PVNL class |
| PSU | PSFO | PCFF | 700 | Tg≈463 K; 700 K = Tg + 237 K ✓ | 15 | rigid biaryl-sulfone backbone; τ_Rouse(dp=15) ≈ 2.5 ns; 15 ns >> τ_Rouse ✓ (wall-time risk) | 8 × 15 | 250–750 K | dp=15; dp@Me(PSU)≈5 (Me≈2380 g/mol); dp=15 >> dp@Me ✓ | Saini2019; Afzal2021 |
| cis-PBD | PDIE | TraPPE-UA | 400 | Tg≈181 K; 400 K = Tg + 219 K ✓ | 3 | flexible rubbery diene; fast equilibration (Sharma2016); τ_Rouse << 1 ns at 400 K | 20 × 100 | 80–400 K | dp=100 >> convergence threshold; Me(PBD) low ✓ | Sharma2016 |
| PEEK | PKTN | PCFF | 770 | Tm≈616 K; 770 K = Tm + 154 K ✓ | 15 | very rigid aryl-ether-ketone backbone; τ_Rouse(dp=15) ≈ 2.2 ns; 15 ns >> τ_Rouse ✓ (wall-time risk) | 8 × 15 | 250–750 K | dp=15; Me(PEEK) not well-known; screening compromise | Chen2025; PEEK2020 |

---

## Protocol notes and screening caveats

### dp < dp@Me — mechanical K is a lower bound (not a protocol failure)

For **aPS (dp=40, dp@Me≈160)**, **PMMA (dp=40, dp@Me≈125)**, and **PVC (dp=60, dp@Me≈160)**: chains
are below the entanglement threshold. Deformation or Murnaghan K values will **systematically
underestimate** the converged bulk modulus by ~30–50%. This is a chain-length artifact, not a force
field failure. Report MD K as a lower bound; flag in paper. Do not swap to a "passing" polymer.

For **PE (dp=120, dp@Me≈80)**: dp > dp@Me ✓. K should be converged within sampling uncertainty.

For **PSU and PEEK (dp=15)**: dp@Me(PSU)≈5 (stiff backbone, low Me), so dp=15 >> dp@Me ✓.
dp@Me(PEEK) is not benchmarked; screening compromise accepted.

### Wall-time risk — PSU and PEEK

Both **PSU (T_equil=700 K)** and **PEEK (T_equil=770 K)** require high equilibration temperatures,
long t_equil=15 ns, and a wide Tg sweep window. These are **verified wall-time risks** in R1:
- Run a pre-check (`scripts/pick_gpu.py budget --mpi 4`) before launching 5-replicate campaigns.
- Consider T_equil + 50 K buffer if density does not converge in 15 ns.

### cis-PBD — MD Tg can fall BELOW experiment (normal for low-fragility rubbers)

**cis-PBD Tg from MD may underestimate experiment**. R1 confirmed: MD Tg = 172.5 K vs exp 181 K
(−8.5 K). This is physically correct for low-fragility rubbery systems where cooperative motion
freezes gradually — the density breakpoint occurs at a lower apparent T in NPT cooling. Do NOT flag
this as a bug or extraction failure.

### PMMA Tg — wrong direction warrants triage before R2

R1 **PMMA1 Tg = 340 K** (exp 378 K, MD always overestimates → **wrong direction**). This requires
triage before R2: check for single-step bug, check extraction method, check whether a PMA-rate run
is being averaged in. Do not treat 340 K as a physics result until root cause is confirmed.

### PVC K — dp<Me entanglement effect

R1 **PVC1 K = 1.68 GPa** vs exp K_T = [3.5, 4.5] GPa (−50%). This is consistent with
dp=60 << dp@Me=160 (under-entangled chains are more compliant). If deform routing was used,
K reflects the short-chain modulus. Murnaghan at 300 K is a better estimator for bulk K, but both
methods underestimate at dp < dp@Me. For R2, increase dp toward 120–160 if wall-time permits.

---

## Exp K_T source summary

All `exp_K_GPa` values in `polymer_rules.json` are K_T (isothermal, PVT/dilatometry) as of
2026-06-21. Conversion rule: K_T = K_S × (Cv/Cp) ≈ K_S × 0.96 (glassy) or × 0.87 (rubbery).

| Polymer | Class | exp K_T [GPa] | Primary source | Mark 2007 Tait K_T [GPa] |
|---------|-------|---------------|----------------|--------------------------|
| PE (amorphous) | PHYC | [1.5, 2.0] | Brandrup & Immergut; Mark 2007 | 1.7–1.9 (above Tg) ✓ |
| aPS | PSTR | [3.3, 4.0] | Mark 2007 Table 7.6 | 3.4–3.7 (glassy) ✓ |
| PMMA | PACR | [3.5, 4.2] | Mark 2007 Table 7.6 | 3.5–3.8 (glassy) ✓ |
| PVC | PVNL | [3.5, 4.5] | Mark 2007 Table 7.6 | ~4.0 (glassy) ✓ |
| PLA | PEST | [3.0, 4.5] | revision.md; no change | — (no Table 7.6 entry) |
| PEG | POXI | [2.0, 4.0] | Mark 2007 Table 7.5 extrapolation | ~2.1 (rubbery, above Tg) |
| cis-PBD | PDIE | [1.38, 1.95] | Mark 1999 PVT; Mark 2007 confirms PI upper | 1.93 (cis-PI) ✓ |
| PEEK | PKTN | [4.0, 5.8] | revision.md (Chen2025; Sahputra2018) | — (no Table 7.6 entry) |
| PSU | PSFO | [4.0, 5.5] | Mark 2007 Table 7.6 (Zoller 1978) | 4.65 (glassy) ✓ |

Note: revision.md K_T ranges for PE [2.5–3.5] and PMMA [4.3–5.4] are from K_S→K_T conversion of
ultrasonic/CROW data. Mark 2007 PVT (true isothermal K_T) gives lower values in both cases.
K_T-priority rule (user confirmed 2026-06-21) means PVT wins — polymer_rules.json uses the PVT-based
ranges, not the ultrasonic-converted ones.
