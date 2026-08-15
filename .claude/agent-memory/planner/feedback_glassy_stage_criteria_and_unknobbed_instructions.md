---
name: glassy-stage-criteria-and-unknobbed-instructions
description: For ct_gate_reliable=false classes never assert overall_pass=True on the equil stage — transcribe BINDING_GLASSY; and when a plan instruction has no tool argument, say so with file:line instead of hiding it in prose
metadata:
  type: feedback
---

Two plan-authoring rules, both from PSU1 critic round 1 (2026-08-13).

**1. `planned_stages[equil].success_criteria` must not carry `check_equilibration_comprehensive.overall_pass: true` for a glassy `ct_gate_reliable=false` class (PSFO, PKTN).** It contradicts D-05's own require_glassy adoption, and `decision_policy.json:policies.equilibration.rationale_glassy` calls `overall_pass=True` "unsatisfiable by construction" for those classes. Write the binding set instead, transcribed from `orchestration/scripts/enforce_gate.py:19-22`: `density_drift, density_sem, energy_drift, energy_sem, density_in_band, density_homogeneity, p2, n_eff_density, finite_size`, plus `overall_pass_not_required: true` and the advisory list `ct, rg, msid_gaussian, msd_not_trapped, residual_stress`.

**Why:** the equil-check stage's `equil_verdict: "PASS"` is a *different* assertion and is NOT in conflict — `enforce_gate.py:93-95` computes the verdict from `binding_results` only and reports `advisory_results` separately, so PASS is attainable with `overall_pass=False`. Keep both, and say why they differ.

**How to apply:**
- Nothing in the plan arms the glassy carve-out. `enforce_gate.py:200-206` reads `polymer_class` from the plan and then pulls `ct_gate_reliable` from `polymer_rules.json`; `resolve_regime()` returns `rubbery` only when `T_workflow_K <= 300`, else `glassy`. So `decided_params.T_workflow_K` is load-bearing for which binding set applies — check it before writing the criteria (700 K ⇒ glassy). Never invent a `decided_params` key to "arm" this.
- `ct_min_decay_melt` non-null (PSFO carries 0.1) still makes `check_equilibration_comprehensive` compute a C(t) pass/fail per `guides/EQUIL_CHECK.md:19-24`, which is exactly why `overall_pass` will be False; `enforce_gate` demotes `ct` by class membership regardless of the threshold. Keep 0.1 so the number is measured, and state this in D-05.

**2. When a plan instruction has no runtime knob, name the absence with file:line and the real channel — don't leave it in a `note`, and don't invent a param.** PSU1's "run Murnaghan with dumps disabled" (51 GB free, below the 60 GB threshold) has no argument: `run_bulk_modulus_series(data_file, work_dir, pressures_atm, temp_K, run_name, gpu_ids, mpi, velocity_seed, npt_steps, dt_fs, use_trappe, use_pcff, use_opls, engine, thermo_freq=100, output_dir=None)` (`mcp-servers/mcp-lammps-engine/server.py:3325-3342`) and `server.py:3436-3437` substitutes `DUMP_FILE`/`LAST_DUMP_FILE` into every per-point script unconditionally. Correct write-up: state the verified signature, state that the orchestrator/murnaghan-worker must strip the dump lines from each generated `.in` at submit time (or delete each `.dump` as the chain advances), and explicitly refuse the decorative key. See [[feedback-decided-params-can-be-decorative]] for why a `bm_dumps_enabled` key would be the wrong fix.

Related: [[psfo-reasoned-plan]], [[planner-scope-denials]].
