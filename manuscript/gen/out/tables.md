## Table 2 — Benchmark systems and experimental references

Single value when one admissible measurement exists, else the band [min–max] over n values (sources and exclusions: gen/references.json).

| Polymer | FF | Host | Tg (K) | ρ (g/cm³) | K_T (GPa) |
|---|---|---|---|---|---|
| PE | trappe-ua | A800 | 195.0–237.0 (n=2) | 0.8550 | 1.780–1.830 (n=2) |
| PEG | pcff | A800 | 213.2 | 1.1183–1.1205 (n=3) | 2.260–2.420 (n=2) |
| PLLA | pcff | RTX6000 | 326.0–337.0 (n=3) | 1.2480 | ungraded |
| aPS | pcff | RTX6000 | 368.1–382.1 (n=9) | 1.0400–1.0650 (n=4) | 3.587 |
| sPVC | pcff | RTX6000 | 378.0–380.0 (n=2) | 1.3850 | 3.860 |
| PEEK | pcff | A800 | 410.0–425.0 (n=4) | 1.2630–1.2650 (n=2) | ungraded |
| PSU | pcff | A800 | 458.1–459.1 (n=3) | 1.2340–1.2350 (n=2) | 4.640 |

## §3.1 — Density at 300 K

Gate-passing cells only. Δ% is measured from the single value, or from the nearer band edge (0 inside the band).

| Polymer | Exp. | ρ mean ± s.d. (n) | Δ% | ±5% | Excluded (gate) |
|---|---|---|---|---|---|
| PE | 0.8550 | 0.8630 ± 0.0035 (3) | +0.9 | ✓ | — |
| PEG | 1.1183–1.1205 (n=3) | 1.0605 ± 0.0037 (2) | -5.2 | ✗ | PEG_2 |
| PLLA | 1.2480 | 1.2300 ± 0.0037 (3) | -1.4 | ✓ | — |
| aPS | 1.0400–1.0650 (n=4) | 0.9876 ± 0.0019 (3) | -5.0 | ✗ | — |
| sPVC | 1.3850 | 1.3462 ± 0.0014 (2) | -2.8 | ✓ | sPVC_2 |
| PEEK | 1.2630–1.2650 (n=2) | 1.2037 ± 0.0019 (3) | -4.7 | ✓ | — |
| PSU | 1.2340–1.2350 (n=2) | 1.1855 ± 0.0019 (3) | -3.9 | ✓ | — |

Melt-vs-glass decomposition (glassy runs with cooling_contraction.json):

| Run | ρ_melt (T) | ρ_300K | expected contraction | actual | shortfall | verdict |
|---|---|---|---|---|---|---|
| PLLA_1 | 1.1022 (620 K) | 1.2341 | 1.1811 | 1.1197 | 0.9479 | UNDER_ANNEALED_COOLING |
| PLLA_2 | 1.1018 (620 K) | 1.2270 | 1.1811 | 1.1137 | 0.9429 | UNDER_ANNEALED_COOLING |
| PLLA_3 | 1.1034 (620 K) | 1.2289 | 1.1811 | 1.1137 | 0.9429 | UNDER_ANNEALED_COOLING |
| aPS_1_rerun | 0.8859 (573 K) | 0.9854 | 1.1383 | 1.1123 | 0.9772 | OK |
| aPS_2 | 0.8856 (573 K) | 0.9882 | 1.1383 | 1.116 | 0.9804 | OK |
| aPS_3 | — (— K) | 0.9891 | 1.1383 | 1.1165 | 0.9808 | OK |
| sPVC_1_rerun | 1.1714 (571 K) | 1.3452 | 1.1378 | 1.1484 | 1.0094 | OK |
| sPVC_2 | 1.1713 (571 K) | 1.3413 | 1.1378 | 1.1452 | 1.0065 | OK |
| sPVC_3 | 1.1716 (571 K) | 1.3472 | 1.1378 | 1.1499 | 1.0107 | OK |
| PEEK_1 | 1.0399 (770 K) | 1.2055 | 1.2407 | 1.1593 | 0.9344 | UNDER_ANNEALED_COOLING |
| PEEK_2 | 1.0401 (770 K) | 1.2017 | 1.2407 | 1.1554 | 0.9313 | UNDER_ANNEALED_COOLING |
| PEEK_3 | 1.0401 (770 K) | 1.2038 | 1.2407 | 1.1574 | 0.9328 | UNDER_ANNEALED_COOLING |
| PSU_1 | 1.0409 (700 K) | 1.1843 | 1.1829 | 1.1378 | 0.9618 | UNDER_ANNEALED_COOLING |
| PSU_2 | 1.0428 (700 K) | 1.1877 | 1.1829 | 1.139 | 0.9628 | UNDER_ANNEALED_COOLING |
| PSU_3 | 1.0415 (700 K) | 1.1846 | 1.1829 | 1.1374 | 0.9615 | UNDER_ANNEALED_COOLING |

PEG force-field arms (round-1 v1 cells, same SMILES/10 chains/300 K; density only — no K was run):

| Arm | Field | ρ (g/cm³) | Δ% vs exp ρ(300 K)=1.1194 |
|---|---|---|---|
| PEG_1–3 (this campaign) | PCFF | 1.0603 ± 0.0026 | -5.28 |
| PEGORE1 | pcff_ore | 1.0557 | -5.69 |
| PEGCMP1 | COMPASS | 1.1241 | +0.42 |

## §3.2 — Glass transition temperature

Means over reportable fits only (TG_REVIEW runs excluded); excluded runs listed per row.

| Polymer | Exp. | Tg mean ± s.d. (n) | ΔTg (K) | ±50 K | Excluded (TG_REVIEW) |
|---|---|---|---|---|---|
| PE | 195.0–237.0 (n=2) | 232.5 ± 8.3 (3) | +0.0 | ✓ | — |
| PEG | 213.2 | 257.3 ± 12.5 (3) | +44.1 | ✓ | — |
| PLLA | 326.0–337.0 (n=3) | 449.3 ± 31.7 (3) | +112.3 | ✗ | — |
| aPS | 368.1–382.1 (n=9) | 422.4 (1) | +40.2 | ✓ | aPS_2 (348.6), aPS_3 (346.7) |
| sPVC | 378.0–380.0 (n=2) | 308.2 ± 12.4 (3) | -69.8 | ✗ | — |
| PEEK | 410.0–425.0 (n=4) | 529.8 ± 31.3 (2) | +104.8 | ✗ | PEEK_2 (572.4) |
| PSU | 458.1–459.1 (n=3) | 477.4 ± 5.6 (2) | +18.2 | ✓ | PSU_2 (525.0) |

Mean |ΔTg| from value or nearest band edge (7 systems): 55.6 K

## §3.3 — Tg sensitivity (predeclared rule: sensitive iff |ΔTg| > pooled within-system replicate s.d.)

- Pooled within-system s.d. (reportable only): **19.5 K** (dof 10)

| Leg | Axis | Rate (K/ns) | Step (K) | Tg (K) | ± | ΔTg vs anchor | Verdict | Sensitive? |
|---|---|---|---|---|---|---|---|---|
| TGS_PE_1_L1_r20 | rate | 20 | 20 | 213.4 | 13.2 | -20.8 vs 234.2 | TG_REPORTABLE | yes |
| TGS_PE_1_L2_r10 | rate | 10 | 20 | 223.1 | 19.7 | -11.1 vs 234.2 | TG_REPORTABLE | no |
| TGS_PE_1_L4_dT10 | t_grid | 20 | 10 | 253.0 | 10.7 | +18.8 vs 234.2 | TG_REPORTABLE | no |
| TGS_PE_1_L5_dT40 | t_grid | 20 | 40 | 208.4 | 19.1 | -25.8 vs 234.2 | TG_REPORTABLE | yes |
| TGS_PLLA_1_L3_r50 | rate | 50 | 20 | 490.0 | 187.7 | +6.4 vs 483.6 | TG_REVIEW (method_gap, gap 78.5 K) | — |
| TGS_PLLA_1_L6_dT40 | t_grid | 100 | 40 | 382.1 | 26.5 | -101.5 vs 483.6 | TG_REPORTABLE | yes |

Anchors: PE_1 at 40 K/ns, 20 K step; PLLA_1 at 100 K/ns, 20 K step. Equilibration-duration and fit-procedure axes: no legs run.

## §3.4 — Bulk modulus at 300 K (Murnaghan)

| Polymer | Exp. K_T | K mean ± s.d. (n) | Δ% | ±30% | Excluded (gate) |
|---|---|---|---|---|---|
| PE | 1.780–1.830 (n=2) | 1.88 ± 0.05 (3) | +3.0 | ✓ | — |
| PEG | 2.260–2.420 (n=2) | 3.30 ± 0.00 (2) | +36.2 | ✗ | PEG_2 |
| PLLA | ungraded | 4.80 ± 0.22 (3) | — | — | — |
| aPS | 3.587 | 2.76 ± 0.11 (3) | -23.0 | ✓ | — |
| sPVC | 3.860 | 2.82 ± 0.10 (2) | -27.0 | ✓ | sPVC_2 |
| PEEK | ungraded | 5.50 ± 0.19 (3) | — | — | — |
| PSU | 4.640 | 4.34 ± 0.27 (3) | -6.4 | ✓ | — |

Murnaghan vs volume-fluctuation K: per-run |divergence| median 6.6%, max 28.1%.

## Table 4 — Equilibration and conformational diagnostics at 300 K (gate-passing cells; n in first column)

| Polymer (n) | ⟨Rg⟩ (Å) | Rg CV (%) | MSID slope | P2 | ρ CV (%) (floor) | E drift (%) |
|---|---|---|---|---|---|---|
| PE (3) | 33.2 ± 2.0 | 19 | 1.11 ± 0.04 | 0.035 ± 0.025 | 10 (19) | 1.94 ± 0.50 |
| PEG (2) | 23.7 ± 0.4 | 19 | 1.02 ± 0.03 | 0.053 ± 0.002 | 20 (29) | 0.67 ± 0.11 |
| PLLA (3) | 16.2 ± 0.9 | 22 | 1.09 ± 0.04 | 0.013 ± 0.005 | 18 (24) | 0.04 ± 0.01 |
| aPS (3) | 14.5 ± 0.4 | 13 | 1.30 ± 0.03 | 0.031 ± 0.013 | 24 (27) | 0.14 ± 0.09 |
| sPVC (2) | 21.7 ± 1.1 | 22 | 1.33 ± 0.01 | 0.030 ± 0.004 | 19 (32) | 2.27 ± 0.70 |
| PEEK (3) | 25.9 ± 0.6 | 22 | 1.26 ± 0.04 | 0.026 ± 0.014 | 16 (22) | 0.08 ± 0.05 |
| PSU (3) | 19.9 ± 2.1 | 19 | 1.13 ± 0.06 | 0.010 ± 0.001 | 18 (23) | 0.11 ± 0.06 |

E drift is the nominal total-energy drift of the 300 K window; it binds only when > 1% AND p < 0.01 (e.g. sPVC_1 4.48%, p = 0.054 → pass).

RDFs (old Figure 6): no RDF output exists for any round-2 run.

## Table 5 — Validation summary (replicate means)

| Property (gate) | PE | PEG | PLLA | aPS | sPVC | PEEK | PSU |
|---|---|---|---|---|---|---|---|
| ρ (±5%) | ✓ +0.9 | ✗ -5.2 | ✓ -1.4 | ✗ -5.0 | ✓ -2.8 | ✓ -4.7 | ✓ -3.9 |
| Tg (±50 K) | ✓ +0.0 | ✓ +44.1 | ✗ +112.3 | ✓ +40.2 | ✗ -69.8 | ✗ +104.8 | ✓ +18.2 |
| K (±30%) | ✓ +3.0 | ✗ +36.2 | — | ✓ -23.0 | ✓ -27.0 | — | ✓ -6.4 |

Scorecard: 13 of 19 — density 5/7, Tg 4/7, K 4/5

## Table 6 — Computational cost per replicate (engine attempt time, all attempts incl. failed/superseded)

| Polymer | FF | Host | GPU-stage h per replicate (range) | of which failed/superseded (sum) | Total GPU-stage h |
|---|---|---|---|---|---|
| PE | trappe-ua | A800 | 3.6–7.1 | 6.1 | 17.0 |
| PEG | pcff | A800 | 12.5–17.4 | 4.9 | 43.3 |
| PLLA | pcff | RTX6000 | 26.0–33.4 | 5.6 | 85.6 |
| aPS | pcff | RTX6000 | 30.8–31.7 | 0.0 | 93.6 |
| sPVC | pcff | RTX6000 | 16.7–17.3 | 0.0 | 50.7 |
| PEEK | pcff | A800 | 14.6–16.3 | 0.0 | 46.9 |
| PSU | pcff | A800 | 14.2–15.6 | 0.0 | 45.3 |

A800: 152 GPU-stage h; RTX6000: 230 GPU-stage h (hosts not pooled: RTX 6000 vs A800 throughput differ; overlapping runs on one card not deconvolved).

## SI S4 — Per-run protocol

| Run | FF | Atoms | DP | n | dt (fs) | cutoff (Å) | T_equil (K) | Tg rate (K/ns) / step (K) | Murnaghan ladder executed (atm) | emc / velocity seed |
|---|---|---|---|---|---|---|---|---|---|---|
| PE_1 | trappe-ua | 3600 | 179 | 10 | 2.0 | 14.0 | 550.0 | 40 / 20 | 1 / 1000 / 2500 / 5000 / 10000 / 15000 | 840238 / 152739 |
| PE_2 | trappe-ua | 3600 | 179 | 10 | 2.0 | 14.0 | 550.0 | 40 / 20 | 1 / 1000 / 2500 / 5000 / 10000 / 15000 | 783028 / 904370 |
| PE_3 | trappe-ua | 3600 | 179 | 10 | 2.0 | 14.0 | 550.0 | 40 / 20 | 1 / 1000 / 2500 / 5000 / 10000 / 15000 | 962891 / 137395 |
| PEG_1 | pcff | 8000 | 114 | 10 | 1.0 | 9.5 | 500.0 | 100 / 20 | -1000 / 0 / 3000 / 7000 / 15000 | 148731 / 135693 |
| PEG_2 | pcff | 8000 | 114 | 10 | 1.0 | 9.5 | 500.0 | 100 / 20 | -1000 / 0 / 3000 / 7000 / 15000 | 798838 / 316927 |
| PEG_3 | pcff | 8000 | 114 | 10 | 1.0 | 9.5 | 500.0 | 100 / 20 | -1000 / 0 / 3000 / 7000 / 15000 | 200187 / 631302 |
| PLLA_1 | pcff | 6320 | 70 | 10 | 1.0 | 9.5 | 620.0 | 100 / 20 | -1000 / 0 / 1500 / 3000 / 5000 | 686928993 / 561359054 |
| PLLA_2 | pcff | 6320 | 70 | 10 | 1.0 | 9.5 | 620.0 | 100 / 20 | -1000 / 0 / 1500 / 3000 / 5000 | 412260453 / 328430378 |
| PLLA_3 | pcff | 6320 | 70 | 10 | 1.0 | 9.5 | 620.0 | 100 / 20 | -1000 / 0 / 1500 / 3000 / 5000 | 967838819 / 25364483 |
| aPS_1_rerun | pcff | 7860 | 49 | 10 | 1.0 | 9.5 | 550.0 | 100 / 20 | -1000 / 0 / 1500 / 3000 | 120191275 / 979826601 |
| aPS_2 | pcff | 7860 | 49 | 10 | 1.0 | 9.5 | 550.0 | 100 / 20 | -1000 / 0 / 1500 / 3000 | 211721699 / 422597568 |
| aPS_3 | pcff | 7860 | 49 | 10 | 1.0 | 9.5 | 550.0 | 100 / 20 | -1000 / 0 / 1500 / 3000 / 5000 | 796234216 / 992835374 |
| sPVC_1_rerun | pcff | 4940 | 41 | 10 | 1.0 | 9.5 | 530.0 | 100 / 20 | -1000 / 0 / 1500 / 3000 / 5000 | 414243003 / 405550636 |
| sPVC_2 | pcff | 4940 | 41 | 10 | 1.0 | 9.5 | 530.0 | 100 / 20 | 0 / 1500 / 3000 / 5000 | 604339280 / 438801734 |
| sPVC_3 | pcff | 4940 | 41 | 10 | 1.0 | 9.5 | 530.0 | 100 / 20 | 0 / 1500 / 3000 / 5000 | 492680472 / 585758416 |
| PEEK_1 | pcff | 6140 | 18 | 10 | 1.0 | 9.5 | 770.0 | 100 / 20 | -200 / 0 / 3000 / 7000 / 15000 | 768489 / 766602 |
| PEEK_2 | pcff | 6140 | 18 | 10 | 1.0 | 9.5 | 770.0 | 100 / 20 | -200 / 0 / 3000 / 7000 / 15000 | 791429 / 898589 |
| PEEK_3 | pcff | 6140 | 18 | 10 | 1.0 | 9.5 | 770.0 | 100 / 20 | -200 / 0 / 3000 / 7000 / 15000 | 973247 / 55037 |
| PSU_1 | pcff | 6500 | 12 | 10 | 1.0 | 9.5 | 700.0 | 100 / 20 | -200 / 0 / 3000 / 7000 / 15000 | 5396 / 836097 |
| PSU_2 | pcff | 6500 | 12 | 10 | 1.0 | 9.5 | 700.0 | 100 / 20 | -200 / 0 / 3000 / 7000 / 15000 | 804277 / 685700 |
| PSU_3 | pcff | 6500 | 12 | 10 | 1.0 | 9.5 | 700.0 | 100 / 20 | -200 / 0 / 3000 / 7000 / 15000 | 675306 / 454398 |

## SI S7 — Per-run Tg

| Run | Tg (K) | ± (K) | R² | fit | width c (K) | verdict (cause) | glassy at 300 K |
|---|---|---|---|---|---|---|---|
| PE_1 | 234.2 | 13.3 | 0.9972 | EXCELLENT | 22.8 | TG_REPORTABLE | False |
| PE_2 | 239.8 | 10.0 | 0.9966 | EXCELLENT | — | TG_REPORTABLE | False |
| PE_3 | 223.5 | 21.2 | 0.9966 | EXCELLENT | 37.4 | TG_REPORTABLE | False |
| PEG_1 | 259.6 | 9.9 | 0.9990 | EXCELLENT | 24.4 | TG_REPORTABLE | False |
| PEG_2 | 268.4 | 12.1 | 0.9991 | EXCELLENT | 58.7 | TG_REPORTABLE | False |
| PEG_3 | 243.8 | 9.3 | 0.9997 | EXCELLENT | 67.0 | TG_REPORTABLE | False |
| PLLA_1 | 483.6 | 21.5 | 0.9974 | EXCELLENT | 82.9 | TG_REPORTABLE | True |
| PLLA_2 | 421.0 | 26.3 | 0.9933 | GOOD | 84.2 | TG_REPORTABLE | True |
| PLLA_3 | 443.2 | 19.9 | 0.9955 | EXCELLENT | 84.5 | TG_REPORTABLE | True |
| aPS_1_rerun | 422.4 | 56.2 | 0.9938 | GOOD | 128.2 | TG_REPORTABLE | True |
| aPS_2 | 348.6 | 16.5 | 0.9966 | EXCELLENT | — | TG_REVIEW (breakpoint_ambiguity) | True |
| aPS_3 | 346.7 | 9.4 | 0.9949 | GOOD | — | TG_REVIEW (breakpoint_ambiguity) | True |
| sPVC_1_rerun | 293.9 | 21.2 | 0.9931 | GOOD | 17.5 | TG_REPORTABLE | False |
| sPVC_2 | 314.3 | 16.8 | 0.9937 | GOOD | — | TG_REPORTABLE | True |
| sPVC_3 | 316.4 | 41.6 | 0.9945 | GOOD | 98.0 | TG_REPORTABLE | True |
| PEEK_1 | 551.9 | 9.0 | 0.9939 | GOOD | 4.8 | TG_REPORTABLE | True |
| PEEK_2 | 572.4 | 19.6 | 0.9841 | GOOD | — | TG_REVIEW (breakpoint_ambiguity) | True |
| PEEK_3 | 507.6 | 7.7 | 0.9967 | EXCELLENT | 4.8 | TG_REPORTABLE | True |
| PSU_1 | 481.3 | 14.7 | 0.9849 | GOOD | 25.6 | TG_REPORTABLE | True |
| PSU_2 | 525.0 | 14.2 | 0.9851 | GOOD | 0.0 | TG_REVIEW (method_gap) | True |
| PSU_3 | 473.4 | 10.2 | 0.9943 | GOOD | — | TG_REPORTABLE | True |

## SI S7 — Per-run density and bulk modulus

| Run | ρ 300 K | ρ melt | K (GPa) ± sem | B0' | R² | points | K_fluct (GPa) | LOO max ΔB0 (%) | ladder convergence |
|---|---|---|---|---|---|---|---|---|---|
| PE_1 | 0.8637 | 0.7189 | 1.890 ± 0.120 | 8.38 | 0.9999 | 6 | 1.77 | 13.7 | BM_LADDER_NOT_CONVERGED |
| PE_2 | 0.8592 | 0.7168 | 1.830 ± 0.157 | 8.27 | 0.9998 | 6 | 1.47 | 15.2 | BM_LADDER_NOT_CONVERGED |
| PE_3 | 0.8661 | 0.7189 | 1.933 ± 0.137 | 8.25 | 0.9998 | 6 | 1.69 | 11.8 | BM_LADDER_NOT_CONVERGED |
| PEG_1 | 1.0579 | 0.9391 | 3.297 ± 0.120 | 9.42 | 0.9999 | 5 | 3.28 | 6.4 | BM_LADDER_CONVERGED |
| PEG_2 | 1.0600 | 0.9378 | 3.534 ± 0.113 | 8.99 | 0.9999 | 5 | 3.63 | 4.5 | BM_LADDER_CONVERGED |
| PEG_3 | 1.0631 | 0.9375 | 3.296 ± 0.123 | 9.58 | 0.9999 | 5 | 3.82 | 6.8 | BM_LADDER_CONVERGED |
| PLLA_1 | 1.2341 | 1.1022 | 4.621 ± 0.167 | 9.78 | 0.9996 | 5 | 5.84 | 7.6 | BM_LADDER_CONVERGED |
| PLLA_2 | 1.2270 | 1.1018 | 4.717 ± 0.059 | 11.40 | 1.0000 | 5 | 4.60 | 3.6 | BM_LADDER_CONVERGED |
| PLLA_3 | 1.2289 | 1.1034 | 5.048 ± 0.172 | 8.54 | 0.9997 | 5 | 5.15 | 5.7 | BM_LADDER_CONVERGED |
| aPS_1_rerun | 0.9854 | 0.8859 | 2.880 ± 0.181 | 7.90 | 0.9988 | 5 | 3.03 | 15.0 | BM_LADDER_NOT_CONVERGED |
| aPS_2 | 0.9882 | 0.8856 | 2.669 ± 0.198 | 9.22 | 0.9984 | 5 | 2.50 | 20.6 | BM_LADDER_NOT_CONVERGED |
| aPS_3 | 0.9891 | — | 2.740 ± 0.094 | 9.70 | 0.9997 | 5 | 3.44 | 9.5 | BM_LADDER_CONVERGED |
| sPVC_1_rerun | 1.3452 | 1.1714 | 2.750 ± 0.094 | 10.01 | 0.9997 | 5 | 3.26 | 10.6 | BM_LADDER_NOT_CONVERGED |
| sPVC_2 | 1.3413 | 1.1713 | 2.627 ± 0.198 | 10.24 | 0.9984 | 5 | 3.36 | 28.1 | BM_LADDER_CONVERGED |
| sPVC_3 | 1.3472 | 1.1716 | 2.888 ± 0.245 | 9.81 | 0.9980 | 5 | 3.27 | 30.2 | BM_LADDER_CONVERGED |
| PEEK_1 | 1.2055 | 1.0399 | 5.729 ± 0.232 | 7.38 | 0.9999 | 5 | 5.06 | 9.1 | BM_LADDER_CONVERGED |
| PEEK_2 | 1.2017 | 1.0401 | 5.383 ± 0.059 | 8.28 | 1.0000 | 5 | 5.52 | 2.1 | BM_LADDER_CONVERGED |
| PEEK_3 | 1.2038 | 1.0401 | 5.402 ± 0.118 | 8.09 | 1.0000 | 5 | 5.63 | 4.5 | BM_LADDER_CONVERGED |
| PSU_1 | 1.1843 | 1.0409 | 4.483 ± 0.115 | 7.76 | 1.0000 | 5 | 3.72 | 2.7 | BM_LADDER_CONVERGED |
| PSU_2 | 1.1877 | 1.0428 | 4.038 ± 0.121 | 8.86 | 0.9999 | 5 | 3.77 | 5.5 | BM_LADDER_CONVERGED |
| PSU_3 | 1.1846 | 1.0415 | 4.511 ± 0.041 | 8.24 | 1.0000 | 5 | 4.71 | 0.8 | BM_LADDER_CONVERGED |

## SI S5 — Per-run gate disposition (frozen gate version)

| Run | Melt: live → old → frozen | Cooling: live → old → frozen | Tg verdict | K ladder | Remedies | Agent calls (actions) | Operator | Critic ran | 300 K props | Tg |
|---|---|---|---|---|---|---|---|---|---|---|
| PE_1 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REPORTABLE | BM_LADDER_NOT_CONVERGED | 1 | 1 (stop) | accepted mechanical | yes | include | include |
| PE_2 | EXTEND → FAIL → **PASS** | EXTEND → FAIL → **FAIL** (n_eff_density) | TG_REPORTABLE | BM_LADDER_NOT_CONVERGED | 0 | 0 +1 archived | accepted mechanical | no | include | include |
| PE_3 | PASS → PASS → **PASS** | EXTEND → FAIL → **FAIL** (n_eff_density) | TG_REPORTABLE | BM_LADDER_NOT_CONVERGED | 0 | 0 +2 archived | accepted mechanical | no | include | include |
| PEG_1 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REPORTABLE | BM_LADDER_CONVERGED | 0 | 0 | — | yes | include | include |
| PEG_2 | PASS → PASS → **PASS** | EXTEND → FAIL → **FAIL** (energy_drift) | TG_REPORTABLE | BM_LADDER_CONVERGED | 0 | 0 +1 archived | — | no | EXCLUDE | include |
| PEG_3 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REPORTABLE | BM_LADDER_CONVERGED | 0 | 0 | — | no | include | include |
| PLLA_1 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REPORTABLE | BM_LADDER_CONVERGED | 1 | 0 +2 archived | 1 repair(s) | yes | include | include |
| PLLA_2 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REPORTABLE | BM_LADDER_CONVERGED | 0 | 0 | — | no | include | include |
| PLLA_3 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REPORTABLE | BM_LADDER_CONVERGED | 0 | 0 | — | no | include | include |
| aPS_1_rerun | None → None → **None** | None → None → **None** | TG_REPORTABLE | BM_LADDER_NOT_CONVERGED | 0 | 0 | — | no | include | include |
| aPS_2 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REVIEW | BM_LADDER_NOT_CONVERGED | 0 | 0 | 1 repair(s) | no | include | EXCLUDE |
| aPS_3 | EXTEND → FAIL → **PASS** | PASS → PASS → **PASS** | TG_REVIEW | BM_LADDER_CONVERGED | 0 | 0 | — | no | include | EXCLUDE |
| sPVC_1_rerun | None → None → **None** | None → None → **None** | TG_REPORTABLE | BM_LADDER_NOT_CONVERGED | 0 | 0 | — | no | include | include |
| sPVC_2 | PASS → PASS → **PASS** | EXTEND → FAIL → **FAIL** (energy_sem) | TG_REPORTABLE | BM_LADDER_CONVERGED | 0 | 0 | — | no | EXCLUDE | include |
| sPVC_3 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REPORTABLE | BM_LADDER_CONVERGED | 0 | 0 | — | no | include | include |
| PEEK_1 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REPORTABLE | BM_LADDER_CONVERGED | 0 | 0 | — | yes | include | include |
| PEEK_2 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REVIEW | BM_LADDER_CONVERGED | 0 | 0 +1 archived | accepted thermal | no | include | EXCLUDE |
| PEEK_3 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REPORTABLE | BM_LADDER_CONVERGED | 0 | 0 | — | no | include | include |
| PSU_1 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REPORTABLE | BM_LADDER_CONVERGED | 0 | 0 | — | yes | include | include |
| PSU_2 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REVIEW | BM_LADDER_CONVERGED | 0 | 0 +1 archived | accepted thermal | no | include | EXCLUDE |
| PSU_3 | PASS → PASS → **PASS** | PASS → PASS → **PASS** | TG_REPORTABLE | BM_LADDER_CONVERGED | 0 | 0 | — | no | include | include |
