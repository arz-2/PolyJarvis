# Born Matrix Guide — REMOVED

Born+NVT has been removed from the PolyJarvis pipeline (2026-06-21).

**Root cause:** PCFF cross-term virial and PPPM kspace contributions inflate K_Born (8–15×)
and Var(P) (~10⁷×) beyond what the formula K_T = K_Born + NkT/V − (V/kT)·Var(P) can
correct. Failed 3/3 in-pipeline runs (PMMA4/0.5 ns, PVC1/0.5 ns, PEEK1/4 ns — the 4-ns run
gave K_T = −49.6 GPa, worse than the 0.5-ns runs). Schnell (2011, *EPJ E*) confirms the
method requires 60,000+ independent configurations for simple pair potentials; PCFF adds
cross-term virial incompatibility on top. Neither problem is fixable at practical run lengths.

**Glassy bulk modulus** is now measured via Murnaghan NPT compression at 300 K (primary) and
3-direction uniaxial deformation (fallback). See `guides/MURNAGHAN.md` and `guides/DEFORM.md`.

**The born-worker agent type** is retained in `.claude/settings.json` for emergency diagnostic
use only and must be explicitly requested by the user — it is **never spawned** by the standard
orchestrator. If K_T < 0 is observed from a diagnostic run, do NOT retry Born with a different
`eq_fraction` or longer `born_run_ns` — the root cause is upstream PCFF virial incompatibility,
not sampling. Route to the deform-worker.
