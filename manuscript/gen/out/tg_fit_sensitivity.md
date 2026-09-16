# Tg fit-procedure sensitivity (analysis-only)

Reproduction of stored Tg with live settings: 22/27 with current extract_thermal.py; the rest by the pre-d76babf code: 5/5 (PE_2, PEEK_1, PEEK_3, PSU_2, PSU_3)
Pooled within-system s.d. (live, reportable fits): 19.5 K

| Procedure | max abs system-mean dTg, all live-reportable runs (K) | systems over threshold | max abs system-mean dTg, runs reportable under both (K) | live-reportable runs made unreportable | sensitive? (all / both-reportable) |
|---|---|---|---|---|---|
| bilinear | 8.7 | — | 7.6 | 9 | no / no |
| hyperbola | 0.0 | — | 0.0 | 0 | no / no |
| eqf_0.25 | 26.4 | aPS | 26.4 | 1 | yes / yes |
| eqf_0.75 | 17.0 | — | 17.0 | 3 | no / no |
| trim_top2 | 53.7 | PLLA | 14.3 | 2 | yes / no |
| trim_bottom2 | 43.6 | aPS | 12.2 | 3 | yes / no |
| reported_code_vs_current | 3.2 | — | 3.2 | 0 | no / no |

## Per-run Tg (K) by procedure

| Run | live | bilinear | hyperbola | eqf_0.25 | eqf_0.75 | trim_top2 | trim_bottom2 | live verdict |
|---|---|---|---|---|---|---|---|---|
| PE_1 | 234.2 | 239.4 | 234.2 | 222.9 | 229.2 | 234.2 | 241.9 | TG_REPORTABLE |
| PE_2 | 239.8 | 243.7 | 239.8 | 244.2 | 239.1 | 242.1 | 241.1 | TG_REPORTABLE |
| PE_3 | 223.5 | 238.3* | 223.5 | 227.1 | 222.0 | 222.9 | 236.2 | TG_REPORTABLE |
| PEG_1 | 259.6 | 265.8 | 259.6 | 261.4 | 247.6 | 262.7 | 269.7 | TG_REPORTABLE |
| PEG_2 | 268.4 | 275.2 | 268.4 | 268.6 | 262.6 | 274.6 | 282.6 | TG_REPORTABLE |
| PEG_3 | 243.8 | 253.5 | 243.8 | 244.5 | 242.2 | 242.6 | 238.4* | TG_REPORTABLE |
| PLLA_1 | 483.6 | 482.7* | 483.6 | 483.8 | 471.8 | 497.9 | 483.0 | TG_REPORTABLE |
| PLLA_2 | 421.0 | 408.9* | 421.0 | 414.7 | 433.7* | 497.1* | 420.5 | TG_REPORTABLE |
| PLLA_3 | 443.2 | 430.2* | 443.2 | 413.4 | 451.8* | 513.8* | 443.2 | TG_REPORTABLE |
| aPS_1 | 422.4 | 414.4* | 422.4 | 396.0 | 405.4 | 409.6 | 466.0* | TG_REPORTABLE |
| aPS_2 | 348.6* | 348.6* | 348.6* | 258.3* | 304.7* | 349.3* | 356.9 | TG_REVIEW |
| aPS_3 | 346.7* | 346.7* | 346.7* | 400.5* | 268.6* | 321.6* | 402.3* | TG_REVIEW |
| sPVC_1 | 293.9 | 296.2* | 293.9 | 282.1 | 296.9 | 294.1 | 295.2 | TG_REPORTABLE |
| sPVC_2 | 314.3 | 310.8* | 314.3 | 323.2 | 318.6 | 313.7 | 318.0 | TG_REPORTABLE |
| sPVC_3 | 316.4 | 319.7* | 316.4 | 373.7* | 322.6* | 309.8 | 288.6* | TG_REPORTABLE |
| PEEK_1 | 551.9 | 552.3 | 551.9 | 552.2 | 573.4 | 555.0 | 553.8 | TG_REPORTABLE |
| PEEK_2 | 572.4* | 572.4* | 572.4* | 584.6* | 515.3* | 562.6* | 574.8* | TG_REVIEW |
| PEEK_3 | 507.6 | 507.3 | 507.6 | 505.1 | 504.9 | 508.7 | 510.5 | TG_REPORTABLE |
| PSU_1 | 481.3 | 486.7* | 481.3 | 490.7 | 484.5 | 481.8 | 481.1 | TG_REPORTABLE |
| PSU_2 | 525.0* | 401.1* | 525.0* | 526.0* | 526.0* | 525.0* | 525.0* | TG_REVIEW |
| PSU_3 | 473.4 | 479.8 | 473.4 | 465.0 | 478.9 | 471.8 | 474.7 | TG_REPORTABLE |
| TGS_PE_1_L1_r20 | 213.4 | 218.7* | 213.4 | 214.4 | 216.7 | 214.2 | 223.9 | TG_REPORTABLE |
| TGS_PE_1_L2_r10 | 223.1 | 234.4* | 223.1 | 225.5 | 231.9 | 217.0* | 237.3 | TG_REPORTABLE |
| TGS_PE_1_L4_dT10 | 253.0 | 254.8 | 253.0 | 252.0 | 258.7 | 253.1 | 256.9 | TG_REPORTABLE |
| TGS_PE_1_L5_dT40 | 208.4 | 210.7 | 208.4 | 199.2 | 207.4 | 205.2 | 242.9 | TG_REPORTABLE |
| TGS_PLLA_1_L3_r50 | 490.0* | 411.5* | 490.0* | 514.4* | 422.3* | 424.3* | 510.9* | TG_REVIEW |
| TGS_PLLA_1_L6_dT40 | 382.1 | 396.9* | 382.1 | 387.2 | 406.6 | 390.6 | 397.5 | TG_REPORTABLE |

\* = not TG_REPORTABLE under that procedure.

Equilibration-duration axis: not controlled (no leg varied the melt hold or per-step time).
