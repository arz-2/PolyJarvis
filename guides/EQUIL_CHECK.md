# Equilibration Check Guide
**Read when:** You are `equilibration-checker` and need to validate the equil chain and extract density.
**Scope:** Equilibration quality check + density extraction only.

---

## Tool: `inspect_data_file` → `backbone_types`

`backbone_types` is **REQUIRED** for `check_equilibration_comprehensive` — do not guess. Call
`inspect_data_file` on the **original pre-simulation `.data` file** (the one EMC/RadonPy wrote,
e.g. the D-00 build result's `data_path` in `run_log.md`) — **never** a `write_data` output like
`equil_data_path`/`npt_prod_data_path`: `write_data` strips the `Masses` section's `# <name>`
comments `atom_type_names` is parsed from, so calling it on a post-simulation file silently
returns no usable names. Atom types are invariant through a run, so the original file's mapping
is still valid. `info.atom_type_names` gives each type's FF label
(e.g. `c`, `c1`, `c_1`, `hc`, `o_1`, `o_2`) and `info.h_type_ids` already excludes hydrogens. Pick
the heavy types that continue the polymer backbone; if a side-group heavy (e.g. a carbonyl O)
could be confused with a backbone one, cross-check with `awk '/^Bonds/,/^Angles/' file.data` —
backbone types appear in chain-continuing bonds. E.g. PEEK = `[1,2,5]` (aromatic C + ether O);
type names starting with `h` are never backbone.

---

## Tool: `check_equilibration_comprehensive`

Returns `overall_pass` and a ready-to-paste `d05_markdown` block.

**Call signature:**
```python
kwargs = dict(
    log_file=npt_prod_log_path,   # production NPT log → thermo convergence (density/energy drift + block-SEM)
    dump_file=melt_dump_path,     # MELT nvt_production.dump (both phases) → C(t)/MSD/Rg/R_ee on mobile chains.
                                  # NOT the production dump: below Tg C(t) never decays (meaningless by construction)
    data_file=equil_data_path,
    backbone_types=backbone_types,
    output_dir=output_dir,
    graphs_dir=graphs_dir,
)
if ct_min_decay_melt is not None:        # null ⇒ aromatic main chain: leave C(t) advisory, do NOT pass ct_min_decay
    kwargs["ct_min_decay"] = ct_min_decay_melt
check_equilibration_comprehensive(**kwargs)
```

**Result fields for the RESULT block** (all from this single call):
- `overall_pass`, `d05_markdown`, `density_converged`, `energy_converged`, `ct_decayed`, `warnings`
- `result["chain"]["ct"]["decay_fraction_at_end"]` → `ct_decay_fraction`
- `result["chain"]["ct"]["tau_relax_ps"]` → `ct_tau_relax_ps`
- `result["chain"]["ree"]["mean_R_ee_A"|"std_R_ee_A"|"n_chains"]` → `end_to_end_r_mean_A` / `_std_A` / `_n_chains`
- C(t)/MSD/R_ee are computed on the melt dump regardless of `ct_min_decay`, so `ct_decay_fraction`/`ct_tau_relax_ps` are always populated — report the actual values even when `ct_min_decay_melt` was null (advisory-only, not N/A).

For PHYC (PE): include `ct_decayed` + `tau_relax_ps` in the RESULT block even on passes.

---

## Tool: `extract_equilibrated_density`

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
starts after the compression ramp. Density passes within ±5% of experimental; **below −5% is
BINDING, not a soft warning.**

## Tool: `enforce_equilibration_gate` — mechanized verdict

Call args are filled in above (search "MECHANIZED GATE"). Call it after the equilibration check
and density extraction write their JSON. **Use its `verdict` field directly — do not re-derive
PASS/EXTEND/FAIL from the raw numbers yourself** (worker prose judgment on this step previously
narrated real violations as false passes — see `manuscript_v2/revision.md` section B).

**The four possible verdicts:**
- **`PASS`** → `equil_verdict=PASS`. (Includes carve-out passes — advisory-only gates failing under
  `require_glassy`/`require_rubbery` do not block.)
- **`EXTEND`** → `equil_verdict=EXTEND`. Only density/energy drift or block-SEM failed — genuinely
  not-yet-converged, more NPT at the same T can fix it.
- **`STRUCTURAL_FAIL`** → `equil_verdict=STRUCTURAL_FAIL` (see FOUNDATION.md for orchestrator
  routing). The cell converged to the *wrong* value, not merely an unconverged one — `EXTEND`
  cannot fix this (a glass cannot densify below Tg). Check the `remedy` field:
  - `re_melt_slow_recool` (from `UNDER_ANNEALED_COOLING`) — melt was fine, cooling ramp too fast.
  - `heavy_melt_anneal_probe` (from `MELT_STAGE_DEFICIT`) — melt itself deficient; re-cooling
    slower will NOT help. Root cause (FF underbinding vs. melt under-annealing) needs the probe.
  - melt-mixing remedy (density_homogeneity failing with density otherwise in-band) — extend
    melt-stage dwell (`melt_npt_steps`/`t_equil_ns`), not the cooling ramp.
- **`FAIL`** → `equil_verdict=FAIL`. Box collapse, charge imbalance, dead cell (C(t) exactly 0%),
  or any binding-gate failure the mechanized script can't classify into the above. (C(t)
  decaying-but-incomplete is reptation-limited, not a FAIL — the script already treats it as
  advisory under the applicable carve-out; you should never see it in `failing_binding_gates`.)

---

## Non-mechanized judgment calls still yours to make

These aren't covered by `enforce_equilibration_gate` (they concern the density/homogeneity NUMBERS
it reads, not the verdict logic) — use judgment here, same as before:

**`extract_equilibrated_density` returns <0.5 g/cm³:** log likely contains the compression ramp — verify `plateau_step_range` after the ramp; raise `eq_fraction` to 0.7.

**Marginal density-homogeneity CV in [24.5%, 25.5%] on a small DP<30 aromatic cell:**
Poisson-limited finite-size noise, not underpacking — the mechanized script will call this a
binding failure (CV≥25% is CV≥25%); if you believe it's Poisson-limited, route as you would an
EXTEND-eligible case manually and note the override explicitly in D-05, don't silently accept.
A co-marginal Rg chain-chain CV (~36%) on the same small cell is the same finite-size noise.

**`check_equilibration_comprehensive` hangs on a large dump (>~1 GB / >1000 frames):**
trajectory I/O can time out. Do NOT block the verdict: rely on `extract_equilibrated_density`
plus the most recent pre-extension comprehensive result — the structural metrics cannot have
moved over a 2 ns 300 K extension of an already-equilibrated cell.
