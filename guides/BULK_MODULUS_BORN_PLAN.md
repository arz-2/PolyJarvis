# Bulk Modulus Improvement Plan: Born + NVT at 300 K

## Background / Motivation

Current glassy-polymer path uses NEMD uniaxial deformation (`npt_deform` template,
`extract_bulk_modulus_deform.py`). Systematic overestimate of ~20–50% due to dynamic
stiffening at MD strain rates (1e7–1e8 s⁻¹ vs quasi-static experiment). The optional
two-rate comparison (Gap 4, `K_rate_comparison` flag in `polymer_rules.json`) spans only
1 decade and cannot extrapolate to quasi-static.

Target accuracy: ±10–15% vs experimental K.

## Physics rationale

- Bulk modulus changes only ~30–40% across Tg (K_rubbery ≈ 2–3 GPa, K_glassy ≈ 3.5–5 GPa).
  The glassy→rubbery collapse is in shear/Young's modulus, not bulk.
- Born + NVT stress fluctuation at 300 K gives the **unrelaxed glassy modulus** —
  the correct quantity for comparison with ultrasonic, Brillouin, and most PVT literature.
- Pressure fluctuations in NVT have ps autocorrelation even in a glass (bond vibrations,
  not chain rearrangements) → converges in 3–5 ns, far cheaper than a 30 M-step slow deform.
- Rate-free: no NEMD, no strain rate artifact.

Formula (NVT ensemble):

    K = K_Born + NkT/V − (V/kT)·Var(P)_NVT

where K_Born is from `compute born/matrix numdiff`.

## LAMMPS capability

- Source: `/home/arz2/lammps/src/EXTRA-COMPUTE/compute_born_matrix.cpp`
- `numdiff` mode: finite differences on virial stress → FF-agnostic (PCFF, OPLS-AA,
  TraPPE-UA all supported; bonds/angles/dihedrals/kspace included automatically)
- **NOT in current `lmp_gpu` binary** — EXTRA-COMPUTE was not compiled in.
- Required: recompile with `-DPKG_EXTRA-COMPUTE=on`

## Implementation steps

1. **Recompile LAMMPS** with `EXTRA-COMPUTE` package enabled.

2. **New Stage 8: NVT-Born production** (glassy polymers only)
   - Input: Stage 7 NPT output `.data` file (`07_npt_production_out.data`)
   - Template: new `nvt_born` template (or extend `npt_production` with `ensemble=nvt`)
   - Adds `compute born/matrix numdiff` + dense `compute pressure` thermo output
   - Run length: 3–5 ns NVT at 300 K
   - Output: born matrix averages + thermo log with pressure column

3. **New analysis script**: `extract_bulk_modulus_born.py`
   - Reads born matrix output → K_Born
   - Reads thermo log → Var(P) → stress-fluctuation correction
   - Applies kinetic term NkT/V
   - Outputs K_GPa, method="born_nvt", uncertainty estimate

4. **Routing change in `property-analysis-worker`**:
   - `is_glassy=True` → Born+NVT path (new Stage 8) instead of NEMD deform
   - `is_glassy=False` → unchanged (NPT volume fluctuation or Murnaghan)
   - Keep NEMD deform as optional cross-check (`deform_crosscheck=true` flag)

5. **`gen_prompt.py` update**: add `--stage born` for the new worker prompt.

6. **Validation**: run one polymer with known K (PMMA or PS) against experimental
   literature before enabling for all classes.
   - If experimental reference is ultrasonic/Brillouin → Born result should match closely
   - If experimental reference is quasi-static PVT → expect ~5–10% systematic offset
     (unrelaxed vs relaxed); document as known bias

## Scope

- Glassy polymers only (is_glassy=True, all 17 classes with K_rate_comparison currently set)
- Rubbery path unchanged
- Two-rate NEMD comparison (Gap 4) can be deprecated once Born path is validated,
  or retained as a fast cross-check

## Open question

Check one experimental K reference for your target polymers: is it from ultrasonic/
Brillouin scattering (unrelaxed) or PVT apparatus (quasi-static)? Determines whether
a systematic correction factor is needed.
