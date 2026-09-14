# PEG1 cross-grade

Generated 2026-09-13T05:23:54+00:00 by `run_cross_grade.py`. Read with the rule in README.md.

| cell | field | chains | RadonPy criteria, native | RadonPy criteria, matched | RadonPy Rg sd_max, matched | PolyJarvis gate (require_rubbery) | dihedral drift |
|---|---|---|---|---|---|---|---|
| radonpy_stock (radonpy) | gaff2_mod | 10 | FAIL — fails rg | INCOMPLETE — not evaluated rg | UNMEASURED | INCOMPLETE — unmeasured density_homogeneity | 0.8976% (p_eff 0.2285, p_naive 0.0) |
| radonpy_retry9 (radonpy) | gaff2_mod | 10 | FAIL — fails rg | FAIL — fails edihed; not evaluated rg | UNMEASURED | INCOMPLETE — unmeasured density_homogeneity (naive p would fail dihedral) | 1.4834% (p_eff 0.1641, p_naive 0.0) |
| PEGCMP1 (polyjarvis) | compass | 10 | FAIL — fails rg; not evaluated dens, eangle, ebond, edihed, elong, evdw, kinene, totene | FAIL — fails rg, totene | FAIL (0.451 vs 0.177 Å) | PASS | 0.2235% (p_eff 0.4619, p_naive 0.0056) |
| PEGORE1 (polyjarvis) | pcff_ore | 10 | FAIL — fails rg; not evaluated dens, eangle, ebond, edihed, elong, evdw, kinene, totene | FAIL — fails eangle, evdw, totene | PASS (0.199 vs 0.200 Å) | PASS (naive p would fail coul) | 0.044% (p_eff 0.6082, p_naive 0.376) |
| PEG2XCMP1 (polyjarvis) | compass | 20 | FAIL — fails rg; not evaluated dens, eangle, ebond, edihed, elong, evdw, kinene, totene | FAIL — fails rg, totene | FAIL (0.351 vs 0.191 Å) | PASS | 0.1179% (p_eff 0.6866, p_naive 0.0449) |
| PEG2XPCF1 (polyjarvis) | pcff | 20 | FAIL — fails rg; not evaluated dens, eangle, ebond, edihed, elong, evdw, kinene, totene | FAIL — fails rg, totene | FAIL (0.241 vs 0.222 Å) | PASS (naive p would fail coul) | 0.0037% (p_eff 0.9635, p_naive 0.9188) |

RadonPy `check_eq` returned True on a window it could not compute: none

RadonPy `check_eq` returned True with no Rg profile, i.e. without its Rg criterion: radonpy_stock (native), radonpy_stock (matched), radonpy_retry9 (native)
