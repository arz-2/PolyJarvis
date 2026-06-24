---
name: peg3-r40-excellent-fit
description: PEG3 r40 (40 K/ns): EXCELLENT fit (R²=0.9994) with Tg=244.4K; well above experimental (206K)
metadata:
  type: reference
---

**Run:** PEG3, cooling rate 40 K/ns (slowest, primary anchor)

**Fit Quality:** EXCELLENT (R² = 0.9994)

**Extracted Tg:** 244.4 K

**Experimental Tg (PEO):** 206 K (from polymer_rules.json POXI class)

**Tg Status:** WARNING — Tg overestimated by +38.4 K (+18.6%) relative to experiment

**CTE:**
- Glassy: 1.846×10⁻⁴ K⁻¹
- Rubbery: 6.306×10⁻⁴ K⁻¹

**ΔCp:** 0.661 J/(g·K) — excellent enthalpy fit (H_r² = 0.9979)

**Observations:**
- Bilinear fit is hyperbola-curvefit (not standard bilinear); physics constraints satisfied (negative slopes, rubbery steeper)
- Tg alternative = 300 K (second intersection); primary fit at 244.4 K is physical
- All n_eff ≥ 7.4 (min relaxation criterion ≥ 5 satisfied across all plateaus)
- 1 plateau skipped for density drift > 1%; 19 plateaus used in final fit
- System mass 44,073.74 g/mol — large polymer system with good equilibration

**Verdict:** EXCELLENT fit quality, but Tg is thermodynamically high vs PEO literature. Possible causes:
1. PCFF may overbind ether oxygen interactions (note in polymer_rules: "PCFF crosses required")
2. PEO Tg may be underestimated in literature (glass transitions are protocol-sensitive); Wu2011 OPLS-AA also gives ~270 K MD Tg (~64 K high)
3. Multirate slope analysis (VF fit) will clarify whether this represents system behavior or rate-dependent artifact

**Next Step:** Extract r160 and r400 rates; compare multirate slope to validate primary Tg anchor.
