# Equilibration Check Guide
**Read when:** You are `equilibration-checker` and need to validate the equil chain and extract density.
**Scope:** Equilibration quality check + density extraction only.

---

## Rules

**`backbone_types`** is **REQUIRED** for `check_equilibration_comprehensive` — do not guess. Derive
it from the **original pre-simulation `.data` file** (the one EMC/RadonPy wrote, e.g. the D-00
build result's `data_path` in `run_log.md`) — **never** a `write_data` output like
`equil_data_path`/`npt_prod_data_path`. `info.atom_type_names` gives each type's FF label
(e.g. `c`, `c1`, `c_1`, `hc`, `o_1`, `o_2`) and `info.h_type_ids` already excludes hydrogens. Pick
the heavy types that continue the polymer backbone; if a side-group heavy (e.g. a carbonyl O)
could be confused with a backbone one, cross-check with `awk '/^Bonds/,/^Angles/' file.data` —
backbone types appear in chain-continuing bonds. E.g. PEEK = `[1,2,5]` (aromatic C + ether O);
type names starting with `h` are never backbone.

`backbone_types` **validates** the backbone, it does not select it. The backbone path is measured
from bond topology (heavy-atom graph diameter), so a wrong selection cannot corrupt P2, MSID,
R_ee or C∞. Report `chain.backbone_path.backbone_type_coverage` — below 0.90 means the types you
passed do not describe this chain's backbone, and the fix is the selection, not the cell.

`ct_min_decay_melt` null ⇒ aromatic main chain: leave C(t) advisory by passing
`ct_min_decay=None` to `check_equilibration_comprehensive`. Pass it explicitly — an omitted
argument and a null one are the same to the tool but not to the record, and only the explicit null
shows the advisory choice was made. C(t)/MSD/R_ee are computed on the melt dump regardless, so
`ct_decay_fraction`/`ct_tau_relax_ps` are always populated — report the actual values even when
`ct_min_decay_melt` was null (advisory-only, not N/A). For PHYC (PE): include `ct_decayed` +
`tau_relax_ps` in the RESULT block even on passes.

Density passes within ±5% of experimental; **below −5% is BINDING, not a soft warning.**

**Use `enforce_equilibration_gate`'s `verdict` field directly — do not re-derive PASS/EXTEND/FAIL
from the raw numbers yourself.** The four possible verdicts:
- **`PASS`** → `equil_verdict=PASS`.
- **`EXTEND`** → `equil_verdict=EXTEND`. Only density/energy drift, block-SEM, or `n_eff_density`
  failed — genuinely not-yet-converged, more NPT at the same T can fix it.
- **`STRUCTURAL_FAIL`** → `equil_verdict=STRUCTURAL_FAIL`. The cell converged to the *wrong*
  value, not merely an unconverged one — `EXTEND` cannot fix this. Check the `remedy` field:
  - `re_melt_slow_recool` (from `UNDER_ANNEALED_COOLING`) — melt was fine, cooling ramp too fast.
  - `heavy_melt_anneal_probe` (from `MELT_STAGE_DEFICIT`) — melt itself deficient; re-cooling
    slower will NOT help.
  - melt-mixing remedy (`density_homogeneity` failing, `homogeneity_verdict=HOMOG_HETEROGENEOUS`) —
    this is what `phase=melt`'s pre-cool gate exists to catch (see Phase below): extend melt-stage
    dwell in place, not the cooling ramp, and never re-melt from scratch. Owned by `/recover`'s
    MELT-MIXING procedure, not this worker.
  - `heavy_melt_anneal_probe` (from `melt_density_verdict=MELT_RHO_DEFICIT`) — the melt itself is
    off experimental ρ(T) by more than the spread across the independent equations for this
    polymer. Cooling changes cannot recover an equilibrium-state deficit. Accepting it as
    force-field bias requires the gap recorded in D-05, flagged unresolved, and at least one
    anneal rung spent — a bare "known PCFF bias" caveat is not sufficient.
  - melt-anneal remedy (`chain_dimensions_verdict=CHAIN_COLLAPSED`) — chains never reached
    Gaussian statistics: `⟨R_ee²⟩/⟨Rg²⟩` is below `0.72×` the finite-N ideal `6N/(N+1)`. Re-run
    with a longer melt hold (`add_melt_npt=True`); a glassy chain does not change shape, so
    extending at 300 K cannot fix it. `CHAIN_EXTENDED` is **not** a failure — backbone stiffness
    legitimately raises the ratio (PSU/PEEK sit above ideal) and the gate binds collapse only.
  - rebuild remedy (`finite_size_verdict=SIZE_MIN_IMAGE_VIOLATION` or `SIZE_CHAIN_SELF_IMAGE`) — the
    box is too small for its own contents: below `2·cutoff_A` the pair potential is wrong, and below
    `2·Rg` every chain overlaps its own periodic images. Raise `nchain` and rebuild; no amount of
    equilibration fixes a too-small box.
- **`FAIL`** → `equil_verdict=FAIL`. Box collapse, charge imbalance, dead cell (C(t) exactly 0%),
  or any binding-gate failure the mechanized script can't classify into the above. (C(t)
  decaying-but-incomplete is not a FAIL — you should never see it in `failing_binding_gates`.)

## Phase

`phase` from the prompt: `full` (default) is today's gate, after the whole equilibration chain
completes, with density extraction and the cooling-contraction diagnosis available. `melt`
(glassy only) runs against `npt_production`/`nvt_production` — the pre-cool checkpoint — *before*
`npt_cool300`/`npt_prod300` are even submitted. `phase=melt` cannot run `assess_cooling_contraction` (no glass state
exists yet), so `UNDER_ANNEALED_COOLING`/`MELT_STAGE_DEFICIT` are unreachable verdicts there —
only the structural/thermo gates that are meaningful on the melt trajectory alone (density/energy
drift, block-SEM, `n_eff_density`, Rg CV, P2, density-homogeneity signal CV, finite size, chain
dimensions, C(t)) can fire. The prompt's `tasks:` list and MECHANIZED GATE args already reflect
which phase you're in — follow them, don't infer.

**`phase=melt` DOES extract density** — against the melt production log at `T_workflow_K`, never
300 K. The mechanized gate grades it against experimental ρ(T) at `T_equil` (Mark 2007 equations in
`db/polymer_db.sqlite`), which needs no glass state, and returns `melt_density_verdict`:
- `MELT_RHO_PASS` — melt density within the reference tolerance.
- `MELT_RHO_DEFICIT` — binding; remedy is `heavy_melt_anneal_probe`, never a slower cooling ramp.
- `MELT_RHO_NO_REFERENCE` — **the gate is UNARMED, which is not a pass.** No equation exists for
  this polymer, or `T_equil` is too far past the fitted range. Common for PSFO/PKTN/PHAL/PIMD.
  Report it as N/A; do not substitute the 300 K band.

Always pass `cutoff_A` from the prompt to `check_equilibration_comprehensive` — it is required,
never optional. It arms the minimum-image half of the finite-size gate (`L ≥ 2·cutoff_A`); omitted,
that half is not evaluated and the verdict rests on the chain-self-imaging criterion (`L ≥ 2·Rg`)
alone. Report `L_over_2cutoff`, `L_over_2Rg`, and `L_over_Ree` in the RESULT block, and report
`min_image_evaluated: false` as a defect in your own invocation, not as a property of the cell.
`L < R_ee` alone is advisory — do not treat it as a failure.

`residual_stress` is reported, never binding. Copy `von_mises_atm`, `z_max`, and `resolved` into the
RESULT block as-is; do not treat a large `z_max` as a failure or re-derive a verdict from it.

---

## Workflow

### `inspect_data_file` → `backbone_types`

Only if `backbone_types` isn't already given in the prompt — call on the original pre-simulation
`.data` file per the Rules above.

### `check_equilibration_comprehensive`

Pass every argument below on every call, including the ones whose value is null. Omitting one is a
schema error, not a default.

```python
check_equilibration_comprehensive(
    log_file=npt_prod_log_path,   # production NPT log → thermo convergence (density/energy drift + block-SEM)
    dump_file=melt_dump_path,     # MELT nvt_production.dump (both phases) → C(t)/MSD/Rg/R_ee on mobile chains.
                                  # NOT the production dump: below Tg C(t) never decays (meaningless by construction)
    data_file=equil_data_path,
    backbone_types=backbone_types,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
    ct_min_decay=ct_min_decay_melt,   # null ⇒ C(t) advisory — pass the null, never omit
    cutoff_A=cutoff_A,                # arms the minimum-image check L ≥ 2·cutoff_A
    timestep_fs=dt_fs,                # must match the deck — sets the ps axis for τ_relax/MSD
)
```

**Result fields for the RESULT block** (all from this single call):
- `overall_pass`, `d05_markdown_path`, `density_converged`, `energy_converged`, `ct_decayed`, `warnings`
- `result["chain"]["ct"]["decay_fraction_at_end"]` → `ct_decay_fraction`
- `result["chain"]["ct"]["tau_relax_ps"]` → `ct_tau_relax_ps`
- `result["chain"]["ree"]["mean_R_ee_A"|"std_R_ee_A"|"n_chains"]` → `end_to_end_r_mean_A` / `_std_A` / `_n_chains`
- `result["chain"]["backbone_path"]["n_backbone_atoms_mean"|"backbone_type_coverage"]`
- `result["chain"]["dimensions"]["verdict"|"ree2_over_rg2"|"ratio_over_ideal"]`
- `result["spatial"]["finite_size"]` → `L_min_A`, `L_over_2cutoff`, `L_over_2Rg`, `L_over_Ree`, `verdict`

### `extract_equilibrated_density`

```python
extract_equilibrated_density(
    log_file=npt_prod_log_path,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
    eq_fraction=0.5,                 # discard first 50% as burn-in
    target_temp=npt_prod_temp_K,     # filter to production-T rows if log is multi-T
)
```
Primary output: `plateau_density_mean` ± `plateau_density_std`. Verify `plateau_step_range`
starts after the compression ramp.

### `enforce_equilibration_gate`

Call args are filled in above (search "MECHANIZED GATE"). Call it after the equilibration check
and density extraction write their JSON.
