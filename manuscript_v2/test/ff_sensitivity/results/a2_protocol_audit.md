# a2 — protocol variation within replicate sets

36 runs across 9 families (sums to 36: True).

A family with a non-empty list below does **not** have a pure-seed replicate set: its reported mean +/- SD mixes protocol variation into what is presented as sampling uncertainty.

| family | n | axes varying | which |
|---|---|---|---|
| PE | 4 | 7 | bm_pressures_atm, charge_method, melt_npt_ns, npt_prod_ns, t_equil_ns, tg_min_steps_per_T, tg_rates_K_per_ns |
| PEEK | 4 | 7 | charge_method, dp_typical, nchain, tg_min_steps_per_T, tg_rates_K_per_ns, tg_t_high_K, tg_t_low_K |
| PEG | 4 | 3 | bm_pressures_atm, charge_method, tg_rates_K_per_ns |
| PLA | 4 | 5 | bm_pressures_atm, charge_method, melt_npt_ns, tg_min_steps_per_T, tg_rates_K_per_ns |
| PMMA | 4 | 4 | charge_method, dp_typical, melt_npt_ns, tg_rates_K_per_ns |
| PS | 4 | 3 | bm_pressures_atm, charge_method, tg_rates_K_per_ns |
| PSU | 4 | 4 | charge_method, dp_typical, nchain, tg_rates_K_per_ns |
| PVC | 4 | 4 | bm_pressures_atm, eq_annealing_cycles, t_equil_ns, tg_rates_K_per_ns |
| cis-PBD | 4 | 4 | bm_pressures_atm, charge_method, tg_min_steps_per_T, tg_rates_K_per_ns |

## Per-axis detail

### PE

- `bm_pressures_atm`: PE1=[1, 100, 300, 600, 1000], PE2=[1, 100, 300, 600, 1000], PE3=[1, 100, 300, 600, 1000], PE4=[1, 500, 1000, 2000, 5000]
- `charge_method`: PE1=Gasteiger, PE2=Gasteiger, PE3=none, PE4=none
- `melt_npt_ns`: PE1=2.0, PE2=2.0, PE3=1.0, PE4=1.0
- `npt_prod_ns`: PE1=10.0, PE2=10.0, PE3=5.0, PE4=5.0
- `t_equil_ns`: PE1=10.0, PE2=10.0, PE3=5.0, PE4=5.0
- `tg_min_steps_per_T`: PE1=None, PE2=None, PE3=100000, PE4=250000
- `tg_rates_K_per_ns`: PE1=[40, 160, 640], PE2=[40, 160, 640], PE3=[25, 50, 100], PE4=[10, 25, 40]

### PEEK

- `charge_method`: PEEK1=RESP, PEEK2=bond-increment, PEEK3=none, PEEK4=none
- `dp_typical`: PEEK1=15, PEEK2=32, PEEK3=32, PEEK4=32
- `nchain`: PEEK1=8, PEEK2=10, PEEK3=8, PEEK4=8
- `tg_min_steps_per_T`: PEEK1=None, PEEK2=None, PEEK3=200000, PEEK4=200000
- `tg_rates_K_per_ns`: PEEK1=[40, 160, 640], PEEK2=[40, 160, 400], PEEK3=[25, 50, 100], PEEK4=[25, 50, 100]
- `tg_t_high_K`: PEEK1=700, PEEK2=700, PEEK3=750, PEEK4=750
- `tg_t_low_K`: PEEK1=350, PEEK2=350, PEEK3=250, PEEK4=250

### PEG

- `bm_pressures_atm`: PEG1=None, PEG2=None, PEG3=None, PEG4=[-1000, 0, 3000, 7000, 15000]
- `charge_method`: PEG1=AM1-BCC, PEG2=none, PEG3=none, PEG4=none
- `tg_rates_K_per_ns`: PEG1=[40, 160, 640], PEG2=[40, 160, 400], PEG3=[40, 160, 400], PEG4=[25, 50, 100]

### PLA

- `bm_pressures_atm`: PLA1=[-1000, -500, 0, 500, 1000], PLA2=None, PLA3=None, PLA4=[-5000, -2500, 0, 2500, 5000]
- `charge_method`: PLA1=RESP, PLA2=none, PLA3=none, PLA4=none
- `melt_npt_ns`: PLA1=None, PLA2=None, PLA3=1.0, PLA4=1.0
- `tg_min_steps_per_T`: PLA1=None, PLA2=None, PLA3=200000, PLA4=200000
- `tg_rates_K_per_ns`: PLA1=[40, 160, 640], PLA2=[40, 100], PLA3=[25, 50, 100], PLA4=[40, 80, 100]

### PMMA

- `charge_method`: PMMA1=RESP, PMMA2=none, PMMA3=none, PMMA4=none
- `dp_typical`: PMMA1=40, PMMA2=50, PMMA3=50, PMMA4=50
- `melt_npt_ns`: PMMA1=None, PMMA2=None, PMMA3=1.0, PMMA4=1.0
- `tg_rates_K_per_ns`: PMMA1=[40, 160, 640], PMMA2=[40, 160, 400], PMMA3=[25, 50, 100], PMMA4=[25, 50, 100]

### PS

- `bm_pressures_atm`: PS1=None, PS2=[-1000, -500, 0, 500, 1000], PS3=[-1000, -500, 0, 500, 1000], PS4=None
- `charge_method`: PS1=RESP, PS2=bond-increment, PS3=bond-increment, PS4=bond-increment
- `tg_rates_K_per_ns`: PS1=[40, 160, 640], PS2=[40, 160, 400], PS3=[40, 160, 400], PS4=[25, 50, 100]

### PSU

- `charge_method`: PSU1=RESP, PSU2=none, PSU3=none, PSU4=none
- `dp_typical`: PSU1=20, PSU2=20, PSU3=25, PSU4=25
- `nchain`: PSU1=8, PSU2=10, PSU3=8, PSU4=8
- `tg_rates_K_per_ns`: PSU1=[40, 160, 640], PSU2=[40, 160, 400], PSU3=[25, 50, 100], PSU4=[25, 50, 100]

### PVC

- `bm_pressures_atm`: PVC1=None, PVC2=None, PVC3=[-1000, 0, 1500, 3000, 5000], PVC4=[-1000, 0, 1500, 3000, 5000]
- `eq_annealing_cycles`: PVC1=5, PVC2=5, PVC3=7, PVC4=7
- `t_equil_ns`: PVC1=5.0, PVC2=5.0, PVC3=8.0, PVC4=8
- `tg_rates_K_per_ns`: PVC1=[40, 160, 400], PVC2=[40, 160, 400], PVC3=[25, 50, 100], PVC4=[25]

### cis-PBD

- `bm_pressures_atm`: cis-PBD1=[1, 100, 300, 600, 1000], cis-PBD2=[1, 100, 300, 600, 1000], cis-PBD3=[1, 100, 300, 600, 1000], cis-PBD4=[1, 500, 1000, 2000, 5000]
- `charge_method`: cis-PBD1=Gasteiger, cis-PBD2=trappe-ua-fixed, cis-PBD3=none, cis-PBD4=none
- `tg_min_steps_per_T`: cis-PBD1=None, cis-PBD2=None, cis-PBD3=100000, cis-PBD4=250000
- `tg_rates_K_per_ns`: cis-PBD1=[40, 160, 640], cis-PBD2=[40, 160, 400], cis-PBD3=[25, 50, 100], cis-PBD4=[10, 25, 40]

