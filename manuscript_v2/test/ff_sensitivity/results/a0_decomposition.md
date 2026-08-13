# a0 — melt/glass decomposition, all glassy families

Reliable: **12 runs** across 3 families (PMMA, PS, PVC).

Unclassified (extrapolation outside validity): 12 (PEEK, PLA, PSU).

Inapplicable (rubbery, no glass state): 12 (PE, PEG, cis-PBD).

| run | span K | rho_melt | rho_glass | glass gap % | melt gap % | shortfall | verdict |
|---|---|---|---|---|---|---|---|
| PE1 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |
| PE2 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |
| PE3 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |
| PE4 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |
| PEEK1 | 470 | 1.0384 | 1.1949 | -5.39 | 2.01 | 0.9275 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PEEK2 | 470 | 1.0541 | 1.1915 | -5.66 | 3.54 | 0.9111 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PEEK3 | 470 | 1.0398 | 1.1973 | -5.2 | 2.14 | 0.9281 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PEEK4 | 470 | 1.0471 | 1.1953 | -5.36 | 2.87 | 0.9201 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PEG1 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |
| PEG2 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |
| PEG3 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |
| PEG4 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |
| PLA1 | 320 | 1.0878 | 1.2350 | -1.2 | 2.79 | 0.9613 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PLA2 | 320 | 1.1005 | 1.2308 | -1.54 | 3.99 | 0.9468 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PLA3 | 320 | 1.0994 | 1.2201 | -2.4 | 3.89 | 0.9395 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PLA4 | 320 | 1.1125 | 1.2319 | -1.45 | 5.12 | 0.9375 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PMMA1 | 250 | 1.0483 | 1.1158 | -6.24 | -1.1 | 0.948 | UNDER_ANNEALED_COOLING |
| PMMA2 | 250 | 1.0633 | 1.1209 | -5.81 | 0.31 | 0.939 | UNDER_ANNEALED_COOLING |
| PMMA3 | 250 | 1.0498 | 1.1197 | -5.91 | -0.96 | 0.95 | UNDER_ANNEALED_COOLING |
| PMMA4 | 250 | 1.0573 | 1.1072 | -6.96 | -0.25 | 0.9328 | UNDER_ANNEALED_COOLING |
| PS1 | 250 | 0.8815 | 0.9828 | -6.4 | -5.6 | 0.9916 | MELT_STAGE_DEFICIT |
| PS2 | 250 | 0.9077 | 0.9832 | -6.36 | -2.79 | 0.9633 | MELT_STAGE_DEFICIT |
| PS3 | 250 | 0.9125 | 0.9849 | -6.2 | -2.28 | 0.9599 | MELT_STAGE_DEFICIT |
| PS4 | 250 | 0.9049 | 0.9896 | -5.75 | -3.09 | 0.9725 | MELT_STAGE_DEFICIT |
| PSU1 | 400 | 1.0451 | 1.1845 | -4.47 | -0.3 | 0.9581 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PSU2 | 400 | 1.0503 | 1.1851 | -4.43 | 0.2 | 0.9538 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PSU3 | 400 | 1.0527 | 1.1869 | -4.28 | 0.43 | 0.9531 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PSU4 | 400 | 1.0433 | 1.1784 | -4.97 | -0.47 | 0.9548 | UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION |
| PVC1 | 230 | 1.2099 | 1.3499 | -2.54 | -2.24 | 0.997 | OK |
| PVC2 | 230 | 1.2027 | 1.3510 | -2.45 | -2.82 | 1.0037 | OK |
| PVC3 | 230 | 1.2237 | 1.3432 | -3.02 | -1.12 | 0.9808 | OK |
| PVC4 | 230 | 1.1793 | 1.3465 | -2.78 | -4.71 | 1.0203 | OK |
| cis-PBD1 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |
| cis-PBD2 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |
| cis-PBD3 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |
| cis-PBD4 | — | — | — | — | — | — | INAPPLICABLE_RUBBERY |

**melt gap above is the alpha heuristic, not a measurement.** `assess_cooling_contraction.py` calls it "only a routing heuristic"; a1 recomputes the melt target from experimental rho(T).
