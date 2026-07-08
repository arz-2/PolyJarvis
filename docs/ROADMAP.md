# PolyJarvis Roadmap

---

## Track C — EMC Validation (C5)
**Classes implemented:** PCBN, PAMD, PKTN, PSFO, PIMD, PSTR (PCFF) · PHAL (OPLS-AA 2024) · PHYC, PDIE (TraPPE-UA)

### C5 — Validation runs
- [x] `PCBN`: BPA-PC — Tg=520 K ✓ (target 500–540 K), ρ=1.168 g/cm³ (−2.7%) · BPAPC1 · 2026-06-03
- [ ] `PAMD`: Nylon-6 — exp Tg ~323 K, target MD Tg 400–440 K · cell ready (bb10f693, 3056 atoms)
- [ ] `PKTN`: PEEK — exp Tg ~418 K, target MD Tg 500–540 K · cell ready (6fe5d5d2, 2728 atoms)
- [ ] `PSFO`: PSU (Udel) — exp Tg ~463 K, target MD Tg 540–580 K · cell ready (3b9b6641, 3246 atoms)
- [ ] `PIMD`: PMDA-ODA (Kapton) — exp Tg ~633 K, target MD Tg 730–810 K · cell ready (0ef810b0, 2946 atoms)
- [x] `PHAL`: PVDF OPLS-AA — Tg=330 K ✓ (target 310–350 K), ρ(300K)=1.528 g/cm³ (−14.2%, worse than GAFF2) · PVDF2 · 2026-06-03 · needs Byutner2000 F params (Track G1)
- [ ] Update `confidence` fields in `polymer_rules.json` after each run

---

## Track D — polymer_rules.json Bookkeeping

- [ ] Add `forcefield_alternatives` array to PHAL, PDIE, PCBN, PAMD, PKTN, PSFO, PIMD
- [ ] Update `confidence` fields after C5 validation results land
- [ ] Add COMPASS II as documented-but-blocked alternative for PIMD/PKTN (license barrier)

---

## Track E — Intelligent FF Selection & Literature Anchoring

### E2 — Literature search for novel / unclassified polymers
- [ ] Implement `search_ff_literature(smiles, polymer_name)` using Semantic Scholar API
- [ ] Add `LIT-01` row to run_log.md template
- [ ] Add `lit_anchor` block: ρ_target, Tg_target, reference FF, DOI
- [ ] Gate on `search_literature=True` (default True for unknown class, False for known)

### E3 — Fast small-cell density screen **[BLOCKED A1/A2]**
- [ ] **[BLOCKED]** Confirm minimum DP/n_chains per class with advisor
- [ ] Once unblocked: `fast_validate=True` flag in equilibration workflow
- [ ] Density tolerance ±10% vs experimental; max 2 FF retries; write RECOVERY block

### E5 — WLF Tg correction (partial)
- [ ] Add `tg_corrected_K` field using WLF correction when literature coefficients available
- [ ] Document correction formula and source DOI in run_log

---

## Track G — Literature-Validated Class Parameters

**Goal:** Build a growing, human-curated library of class-specific force field parameters validated against experiment, encoded in `polymer_rules.json` and eventually consumed by the pipeline to improve simulation accuracy. Distinct from Track E (automated runtime search) — Track G is statically encoded, versioned, and citeable.

### G0 — Schema: `class_params` + `wlf_params` in polymer_rules.json
- [ ] Add optional `class_params` object to each class entry (keyed by polymer name, e.g. `"PVDF"`)
- [ ] Each `class_params` entry records: `ff_name`, `functional_form`, `implementation_status` (`"planned"` / `"available"` / `"experimental"`), `source_doi`, `nonbonded_params`, `charges`, `cutoff_A`, `dt_fs`, `validation_targets`, `known_default_error`
- [ ] Add `wlf_params` object to each class entry (merges E5): per-polymer WLF C1/C2/T_ref with `source` and `validated` flag
- [ ] Create `guides/LITERATURE_PARAMS.md`: human-readable rationale paragraph for each `class_params` entry (one paragraph per polymer, written at time of encoding)

### G1 — Priority scanning queue (encode in order)

| Priority | Class | Polymer | Source | Parameter gap |
|---|---|---|---|---|
| 1 | PHAL | PVDF | Byutner & Smith, *Macromolecules* 2000, 33, 4264 | H−F Buckingham-6 nonbonded; OPLS-AA gives −9% density error |
| 2 | PHYC | PE | Martin & Siepmann *J. Phys. Chem. B* 1998; Ramos et al. *Macromolecules* 2015 | TraPPE-UA α=8.57×10⁻⁴ K⁻¹ validated |
| 3 | PSTR | PS | Keasler et al. *J. Phys. Chem. B* 2012, 116, 11234 | TraPPE-UA PS, Tg 373 K |
| 4 | PAMD | Nylon-6 | Tang & Okazaki *Polymer* 2022, 253 | PCFF Nylon-6 Tg 313 K |
| 5 | PKTN | PEEK | needs survey | PCFF PEEK Tg 417 K |
| 6 | PCBN | BPA-PC | Tang & Okazaki *Polymer* 2022 | PCFF PC density 1.20 g/cm³ |

### G2 — Scanning protocol (apply for each G1 entry)
1. Paper must report ≥1 validated property (density or Tg) with ≤5% error on amorphous MD
2. Extract: functional form, nonbonded params (ε/σ or A/B/C), charges, cutoff, timestep, SHAKE settings, validation targets
3. Encode into `class_params` with `implementation_status: "planned"` and `source_doi`
4. Write one-paragraph entry in `guides/LITERATURE_PARAMS.md`

### G3 — Pipeline integration (deferred until ≥3 `"available"` entries)
- [ ] Stage 1 (molecule-builder): append `lammps_patch` block to job output when `class_params` entry exists with `"available"` status
- [ ] Stage 2 (equilibration-worker): inject `lammps_patch` overrides (pair_style, pair_coeff, charges) before submitting
- [ ] Update CLAUDE.md dispatch table: "check `class_params` before spawning equilibration-worker; pass `lammps_patch` in prompt if present"
- **Note:** Byutner2000 PVDF requires `buck/coul/long` — different pair_style from `lj/cut/coul/long`. Non-trivial; deferred to G3.

### G4 — WLF coefficient registry (merges E5)
- [ ] Add `wlf_params` per-class to polymer_rules.json alongside `class_params`
- [ ] E5 in Priority Order becomes a pointer here; WLF correction applied in analysis using per-class C1/C2

---

## Track H — Advanced Chain Architectures

RadonPy supports random, block, and blend cell construction but these are not yet exposed as MCP tools. The alternating copolymer path (`submit_copolymerize_job`) is the only implemented copolymer route.

### H1 — Statistical copolymers
- [ ] Implement `submit_random_copolymerize_job(mol_files, ratio, degree_of_polymerization, ratio_type, tacticity)`
  - `ratio` auto-normalised; `ratio_type='exact'` enforces composition, `'choice'` is probabilistic
  - Wraps `poly.polymerize_rw` with a random sequence generator

### H2 — Block copolymers
- [ ] Implement `submit_block_copolymerize_job(mol_files, block_lengths, tacticity)`
  - `mol_files` and `block_lengths` are parallel arrays
  - ABA triblock: pass same monomer file twice with two entries in `block_lengths`

### H3 — Polymer blends / mixture cells
- [ ] Implement `submit_generate_mixture_cell_job(mol_files, chains_per_component, density, temperature)`
  - Takes fully-polymerised, FF-assigned polymer JSONs (distinct from `submit_generate_copolymer_cell_job`)
  - `chains_per_component[i]` controls stoichiometry
  - Use cases: miscibility studies, polymer/solvent mixtures, multi-component blends

### H4 — Stage 1 guide updates (do after H1–H3 land)
- [ ] Re-add tool sections to `MOLECULE_BUILDER.md` with working examples
- [ ] Update `docs/TOOLS_REFERENCE.md` Mol-Builder Server table
- [ ] Add routing logic to molecule-builder agent for non-alternating copolymers

---

## Track I — Analysis / Property Extraction Improvements

### I1 — Bulk modulus: replace B_dyn with multi-pressure Murnaghan EOS

**Evidence (PE4 run, 2026-06-02):** B_dyn from single-point NPT volume fluctuations = 0.607 GPa; Murnaghan B0 from 5-point pressure series = 0.401 ± 0.005 GPa (R²=0.99995, B0'=10.7). Disagreement 34%. Root cause: (1) for soft polymer melts with large B0' (~10), the EOS is strongly nonlinear even at 1–1000 atm — linear P vs ln V fails (R²=0.968); (2) B_dyn is biased high by barostat damping (P_DAMP=1000 fs constrains volume fluctuations). The multi-pressure series adds ~20 min wall time for a 2400-atom system.

**Status (2026-06-16):** Core tools shipped (`run_bulk_modulus_series`, `extract_bulk_modulus_murnaghan.py`, `bm_pressures_atm` for PHYC/PDIE). Remaining: doc updates + RESULTS table field.

- [ ] Update `docs/TOOLS_REFERENCE.md`: replace B_dyn description with Murnaghan series protocol
- [ ] Update `murnaghan-worker.md`: document Murnaghan as default for rubbery + bm_pressures_atm set
- [ ] Add `B0_prime` field to RESULTS table in `data/TEMPLATE/run_log.md`

---

### I2 — Bulk modulus: adaptive pressure selection + method unification decision

**Update (2026-06-24):** The unification question below is resolved — Murnaghan EOS is the primary path for **both** glassy (NPT compression at 300 K) and rubbery (T>Tg) polymers, with 3-direction uniaxial deformation as the fallback when a Murnaghan fit fails acceptance. The remaining live work is the adaptive pressure-range selection (I2-B/C/E).

**Context (2026-06-16):** Method routing is class-specific: only PHYC and PDIE have `bm_pressures_atm` set. The pressure ranges are hardcoded guesses, not derived from the polymer's stiffness. This is the current gap.

**Method assessment:**

| Method | Phase | GPU | Rate artifact | Status |
|--------|-------|-----|---------------|--------|
| Murnaghan EOS sweep (NPT) | Both | Yes | None | **Primary (glassy + rubbery)** |
| Volume fluctuation | Rubbery | Yes | None (but barostat-sensitive) | Cross-check only |
| 3-direction uniaxial deformation | Both | Yes | ~20–50% overestimate | Fallback (Murnaghan fit fails) |

The EOS sweep is GPU-compatible and works in both phases — Morikami 1996 (Fig. 3, PE at 150 K < Tg) shows a well-behaved P-V response in the glassy state at moderate pressures, confirming the EOS holds below Tg. It is therefore the unified primary path; deformation is the fallback when a Murnaghan fit fails acceptance (`fit_converged=False` or `B0_prime` outside [4, 20]).

**Agentic mechanism — strain-targeted adaptive pressure selection:**

The current pain is that `bm_pressures_atm` is a hardcoded per-class list. An agent can derive the range automatically by targeting a fixed volumetric strain (~1–2%) rather than a fixed pressure:

```
1. Pilot: 2 NPT points at P = [1, P_pilot] atm
   P_pilot = exp_K_GPa × 0.01 × 9869   (1% strain in atm)
   If exp_K_GPa not set: default P_pilot = 500 atm

2. Estimate K_rough = −V̄ × ΔP / ΔV

3. Select full sweep: 5 points spanning ±2% volumetric strain
   P_range = K_rough × 0.02   (in GPa, convert to atm)
   pressures = linspace(−P_range/2, +P_range/2, 5)  centered on 1 atm

4. Run Murnaghan fit → check R² ≥ 0.999

5. If R² < 0.999: add 2 outer points, re-fit. Max 2 extension rounds.
```

This is system-agnostic: a stiff glass (K ~ 4 GPa) automatically uses a wide pressure range; a soft melt (K ~ 0.3 GPa) uses a narrow one. No per-class configuration needed.

**Implementation plan:**

- [x] **I2-A — glassy BM method decision**: Murnaghan EOS adopted as the primary glassy path (300 K NPT compression); 3-direction deformation is the fallback when a fit fails acceptance.
- [ ] **I2-B — Adaptive pressure selection in `murnaghan-worker`**: replace per-class `bm_pressures_atm` lookup with pilot-based range computation (2 pilot points → K_rough → 5-point sweep). Keyed to `exp_K_GPa` from `polymer_rules.json`; falls back to 500-atm pilot if field absent.
- [ ] **I2-C — R²-based extension loop**: add `max_extensions=2` loop to `murnaghan-worker` that appends outer pressure points if Murnaghan R² < 0.999.
- [x] **I2-D — Glassy fallback**: 3-direction uniaxial deformation is the glassy fallback, invoked when a Murnaghan fit fails acceptance (`fit_converged=False` or `B0_prime` outside [4, 20]).
- [ ] **I2-E — Remove hardcoded `bm_pressures_atm`** from polymer_rules.json once I2-B is live (PHYC and PDIE). Keep `exp_K_GPa` — that drives the adaptive range.

**Decision gate:** I2-B/C/E (adaptive pressure selection) are the remaining live work.

---

## Track J — Additional Physical Properties

### J1 — Coefficient of Thermal Expansion (CTE)

**Rationale:** α_glass and α_rubber are already implicit in the bilinear Tg fit — they are the slopes of the glassy and rubbery branches of the density-vs-T curve. Reporting them costs zero additional simulation time and provides two well-tabulated experimental targets (VanKrevelen Ch. 5; Polymer Handbook).

```
α_glass  = −(1/ρ) × (dρ/dT)_glassy_branch     [K⁻¹]
α_rubber = −(1/ρ) × (dρ/dT)_rubbery_branch    [K⁻¹]
```

The ratio α_rubber/α_glass ≈ 2–3 is a universal polymer physics result and serves as a built-in sanity check on the bilinear fit. Typical MD error: <15% for both branches.

**Implementation plan** (shipped: CTE/ΔCp in `extract_thermal`, RESULTS rows, `PROPERTIES.md`, worker surfacing):
- [ ] Add `experimental_cte_glass_1e-5_per_K` and `experimental_cte_rubber_1e-5_per_K` fields to polymer_rules.json for each class (source: VanKrevelen2009 Ch.5, Polymer Handbook)

**Artifact note:** Fast MD cooling rate shifts the Tg breakpoint but does not strongly bias branch slopes — CTE error is decoupled from the Tg offset artifact.

---

### J2 — Cohesive Energy Density / Hildebrand Solubility Parameter

**Rationale:** δ = √(E_pair / V) is a one-line post-process on the existing NPT production log. Experimental values are in Barton's CRC Handbook for nearly every revision polymer. Useful for solvent compatibility screening.

```
CED = E_pair / V          (J/cm³)
δ   = √CED                (MPa^0.5)
```

**Artifact note:** For PCFF `lj/class2` pair_style, `e_pair` in LAMMPS thermo includes 1–4 intramolecular pairs — verify these are subtracted or negligible before reporting. Validate against PMMA (δ_exp ≈ 19.4 MPa^0.5) before enabling for other classes. Gasteiger-charged systems (apolar TraPPE-UA classes) may show 20%+ error; flag `charge_method` from polymer_rules.json in the output.

**Implementation plan:**
- [ ] Add `extract_solubility_parameter(log_path, output_dir)` tool to `mcp-lammps-engine/server.py`
  - Reads `e_pair` and `vol` thermo columns from NPT production log
  - Computes CED = mean(e_pair) / mean(vol); δ = √CED in MPa^0.5
  - Emits warning if `charge_method == "Gasteiger"` (confidence degraded)
- [ ] Validate E_pair decomposition for PCFF on PMMA4 run before wiring into pipeline
- [ ] Add `experimental_solubility_param_MPa05` field to polymer_rules.json for each class
- [ ] Add δ row to RESULTS table in `data/TEMPLATE/run_log.md`
- [ ] Add `--properties solubility_param` flag support to `gen_prompt.py` and `PROPERTIES.md`

---

### J3 — Thermal Conductivity (Green-Kubo NVT)

**Rationale:** DB already has λ entries for PMMA (0.193 W/m·K), PSU (0.26), PEEK (0.25) — the experimental targets exist. Green-Kubo from a 5–10 ns NVT run is the standard path.

```
λ = (1 / 3kTV) ∫₀^∞ ⟨J_q(t)·J_q(0)⟩ dt
```

**Artifact note:** PCFF systematically overestimates λ by ~15–25% for most polymers (known Class II artifact for thermal transport). The ACF integral is noisy — variance ~20–30%; requires block-averaging over ≥3 independent runs or one ≥10 ns trajectory. Convergence is size-independent above ~1000 atoms.

**Implementation plan (deferred — do after J1 and J2 land):**
- [ ] Add `nvt_gk` LAMMPS template: NVT at 300 K, `compute heat/flux`, `fix ave/correlate`, 10 ns
- [ ] Add `tc-worker` agent: submits `nvt_gk` from Stage 7 NPT data file; returns run_id
- [ ] Add `extract_thermal_conductivity(log_path, output_dir)` tool: reads ACF output, integrates, block-averages, returns λ ± σ in W/m·K
- [ ] Add `experimental_tc_W_per_mK` field to polymer_rules.json for classes with DB entries
- [ ] Wire into orchestrator as an optional Stage after bulk-modulus-extractor (only if `thermal_conductivity` in properties_requested)
- [ ] Add λ row to RESULTS table in `data/TEMPLATE/run_log.md`

---

## Track K — Planner / Critic Architecture

**Goal:** Separate **planning** (open-ended, reasoned, evidence-justified) from **execution** (never improvises). Each run produces a structured pre-execution artifact, `data/[RUN]/raw/run_plan.json`, that is challenged by a Critic before any simulation launches. Planning *depth* is gated on the existing per-class `confidence` field so validated, fixed-seed replication runs are never disturbed. Most of the underlying philosophy was already shipped (explicit state artifacts, per-decision confidence/DOI, `electrostatics_decision_guide`, `check_equilibration_comprehensive`); Track K closes the one real gap — there was no planner/critic separation and no pre-execution plan artifact.

**Control flow:** `Planner → run_plan.json → Critic (approve/revise/escalate) → Executor (steps 4–16) → Validator (stage-gate) → KB update`.

**Confidence gate** (in `guides/decision_policy.json`): `confidence=high` → deterministic plan (defaults transcribed verbatim, critic auto-approves, worker prompts byte-identical to the legacy pipeline). `confidence=low/medium` or off-table polymer → reasoned plan (each decision carries evidence/confidence/alternatives; Critic enforces the policy; loop ≤2 rounds).

### K0–K2 **[done 2026-06-17]**
Shipped: `guides/decision_policy.json`, `orchestration/make_deterministic_plan.py`, `gen_prompt.py --plan`
overlay, `tests/test_plan_reproducibility.py` (prompt-identity guard), planner/critic agents +
CLAUDE.md Planner → Critic loop, validator stage-gate against `planned_stages[].success_criteria`,
`generate_run_summary.py --run_plan`, and the run_log PLAN pointer.
- [ ] Post-validation `confidence` field update via `/ingest-memory` (merges with Track D bookkeeping)

### K3 — Follow-ups (deferred)
- [ ] Wire the reasoned-path probes to live capabilities as they land: `literature_anchor` → E2, `fast_density_screen` → E3 (BLOCKED A1/A2)
- [ ] End-to-end validation: one high-confidence fixed-seed class (PHYC/PE) must reproduce a prior run; one medium/low class (PAMD) must produce an evidence-bearing reasoned plan

---

## Priority Order

| Priority | Track | Status | Notes |
|---|---|---|---|
| **1** | C5 — Validation runs | Partial | PCBN + PHAL validated; PKTN/PSFO since exercised at scale by the 36-run benchmark study; PAMD/PIMD cells queued |
| **2** | E2 — Literature search | Pending | Needed before expanding beyond known classes (literature-grounding-worker covers the planning side) |
| **3** | D — rules bookkeeping | Pending C5 | Confidence fields; do after C5 results |
| **4** | G0 — class_params schema | Pending | Schema first; no pipeline changes yet |
| **5** | G1 — Literature scanning | Pending G0 | PVDF first; encode 6 classes in order |
| **6** | E3 — Fast density screen | **Blocked** | Needs advisor input A1/A2 |
| **7** | H — Advanced chain architectures | Pending | Random/block copoly + blends; unblocked |
| **8** | I1 — Murnaghan doc updates | Partial | Tools done; doc updates + B0_prime field remain |
| **9** | I2-B/C — Adaptive pressure selection + R² extension | Pending | Removes all hardcoded bm_pressures_atm; makes sweep system-agnostic |
| **10** | J2 — Solubility parameter δ | Pending | E_pair/V post-process on NPT log; validate on PMMA first |
| **11** | J3 — Thermal conductivity λ | Pending J2 | New nvt_gk template + tc-worker; exp targets exist for PMMA/PSU/PEEK |
| **—** | K3 — Planner/critic follow-ups | Deferred | Probe wiring (E2/E3) + end-to-end validation; K0–K2 shipped |
| **—** | L — Future tracks (taxonomy) | Planned | Electrical (ε, dipole), Viscoelastic (E', E'', tan δ), Transport (D, permeability) — no workers yet |
