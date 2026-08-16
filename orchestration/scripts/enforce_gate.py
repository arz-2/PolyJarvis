#!/usr/bin/env python3
"""Mechanized D-05 gate-verdict enforcement.

Cross-checks a completed equil run's overall_pass + per-gate results against
decision_policy.json's require_glassy / require_rubbery / plain-require clauses,
programmatically -- not via worker prose. Also applies density_value_binding
(assess_cooling_contraction must have run when 300K density falls >5% below
experiment) and lints run_log.md for an unfilled D-05 template placeholder.

Usage: python3 enforce_gate.py <run_name> [--repo-root PATH]
Prints a JSON verdict to stdout: PASS_CLEAN | PASS_CARVEOUT | VIOLATION | UNADJUDICATED.
"""
import argparse
import json
import re
import sys
from pathlib import Path

BINDING_GLASSY = {"density_drift", "density_sem", "energy_drift", "energy_sem",
                   "density_in_band", "density_homogeneity", "p2", "n_eff_density",
                   "finite_size"}
ADVISORY_GLASSY = {"ct", "rg", "msid_gaussian", "msd_not_trapped", "residual_stress"}

BINDING_RUBBERY = {"density_sem", "density_homogeneity", "energy_drift", "energy_sem",
                   "n_eff_density", "finite_size"}
ADVISORY_RUBBERY = {"ct", "rg", "msid_gaussian", "msd_not_trapped", "density_drift",
                    "residual_stress"}
# density_drift isn't in require_rubbery's binding text (density_sem is); treated advisory here.

# MSD diffusivity metrics are advisory everywhere, unconditionally -- decision_policy.json's
# rationale_glassy/rationale_rubbery (2026-06-20, user-authorized, PVC1 route-back) documents
# that melt self-diffusion is physically unattainable within MD timescales for glassy DP>=30 /
# aromatic-backbone classes and for rubbery polymers generally, so binding on it would make
# overall_pass unsatisfiable by construction. classify()'s plain-require branch defaults every
# gates key to binding; this carve-out is applied there too, explicitly -- not decided as a
# side effect of dict membership.
#
# residual_stress joins them for the same class of reason, but by calibration status
# rather than by physics: a resolved deviatoric stress IS a genuine mechanical-equilibrium
# violation (glassy cells carry 100-290 atm, 10-29% of the +/-1000 atm Murnaghan increment,
# while their melts are stress-isotropic), but every archived glassy run violates it to some
# degree, so binding it before the magnitude bound is calibrated would halt the whole glassy
# track. It is emitted and logged now; promote to STRUCTURAL_GATES once the bound is set.
ALWAYS_ADVISORY = {"msd_not_trapped", "msid_gaussian", "residual_stress"}

D05_PLACEHOLDER_RE = re.compile(r"\[PASS\s*/\s*EXTEND[×x]N\s*/\s*ESCALATE\]", re.IGNORECASE)


def load_json(path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def resolve_regime(t_workflow_k):
    return "rubbery" if t_workflow_k is not None and t_workflow_k <= 300.0 else "glassy"


def density_in_band(plateau_mean, exp_field, polymer_key, band_pct=5.0):
    if plateau_mean is None or exp_field is None:
        return None, None, None
    if isinstance(exp_field, (int, float)):
        exp_val = exp_field
    elif isinstance(exp_field, dict):
        exp_val = exp_field.get(polymer_key)
    else:
        exp_val = None
    if exp_val is None:
        return None, None, None
    gap_pct = 100.0 * (plateau_mean - exp_val) / exp_val
    return abs(gap_pct) <= band_pct, gap_pct, exp_val


def _stage_log_for(data_path):
    """<stage>/<stage>_out.data -> <stage>/<stage>.log, or None if it isn't there."""
    if not data_path:
        return None
    p = Path(data_path)
    if not p.name.endswith("_out.data"):
        return None
    log = p.with_name(p.name[: -len("_out.data")] + ".log")
    return str(log) if log.exists() else None


def classify(gates: dict, regime: str, dp_typical, ct_gate_reliable):
    """Shared clause-selection + binding/advisory split, used by both the retrospective
    (enforce) and live (enforce_live) paths."""
    if regime == "glassy" and (
        (dp_typical is not None and dp_typical >= 30) or ct_gate_reliable is False
    ):
        clause = "require_glassy"
        binding_set, advisory_set = BINDING_GLASSY, ADVISORY_GLASSY
    elif regime == "rubbery":
        clause = "require_rubbery"
        binding_set, advisory_set = BINDING_RUBBERY, ADVISORY_RUBBERY
    else:
        clause = "require (plain, no carve-out)"
        binding_set, advisory_set = set(gates.keys()), set()

    binding_set = binding_set - ALWAYS_ADVISORY
    advisory_set = advisory_set | ALWAYS_ADVISORY

    binding_results = {k: v for k, v in gates.items() if k in binding_set and v is not None}
    advisory_results = {k: v for k, v in gates.items() if k in advisory_set and v is not None}
    return clause, binding_results, advisory_results


def collect_gates(comp: dict) -> dict:
    """Pull every per-gate pass boolean out of equilibration_comprehensive.json.

    Single source of truth for both enforce() and enforce_live() -- a gate key added to
    only one of them would be a silent no-op in the other path.
    """
    thermo = comp.get("thermo", {})
    chain = comp.get("chain", {})
    spatial = comp.get("spatial", {})
    return {
        "density_drift": thermo.get("density_drift", {}).get("pass"),
        "energy_drift": thermo.get("energy_drift", {}).get("pass"),
        "density_sem": thermo.get("density_sem", {}).get("pass"),
        "energy_sem": thermo.get("energy_sem", {}).get("pass"),
        "n_eff_density": thermo.get("n_eff_density", {}).get("pass"),
        "residual_stress": residual_stress_gate(thermo),
        "rg": chain.get("rg", {}).get("pass"),
        "ct": chain.get("ct", {}).get("pass"),
        "p2": spatial.get("p2", {}).get("pass"),
        "density_homogeneity": spatial.get("density_homogeneity", {}).get("pass"),
        "finite_size": finite_size_gate(spatial),
        **msd_msid_gates(chain),
    }


def residual_stress_gate(thermo: dict):
    """Pass-polarity entry for the mechanical-equilibrium check -- advisory (see
    ALWAYS_ADVISORY). None when the log carried no pressure tensor. Never thresholds
    z, which grows as sqrt(n); `resolved` only says the deviatoric stress is measurable."""
    rs = thermo.get("residual_stress") or {}
    if not rs.get("available"):
        return None
    return not rs.get("resolved", False)


def finite_size_gate(spatial: dict):
    """Pass-polarity entry for the periodic self-imaging checks. None when the box or Rg
    could not be measured. Binding and STRUCTURAL: neither a minimum-image violation nor a
    chain overlapping its own image can be fixed by sampling longer -- the cell is wrong."""
    fs = spatial.get("finite_size") or {}
    if not fs.get("available"):
        return None
    return fs.get("pass")


def finite_size_verdict(comp: dict):
    """SIZE_MIN_IMAGE_VIOLATION | SIZE_CHAIN_SELF_IMAGE | SIZE_PASS | None."""
    fs = (comp.get("spatial") or {}).get("finite_size") or {}
    return fs.get("verdict") if fs.get("available") else None


def finite_size_min_image_unarmed(comp: dict) -> bool:
    """True when the gate ran but L >= 2*cutoff_A was never evaluated (no cutoff_A passed).

    A SIZE_PASS then rests on the 2*Rg criterion alone. Surfaced so the omission cannot sit
    unnoticed: minimum image is cleared by 2-3x on realistic cells, so its silent
    non-evaluation almost never changes a verdict, which is exactly why it can stay broken.
    """
    fs = (comp.get("spatial") or {}).get("finite_size") or {}
    return bool(fs.get("available") and not fs.get("min_image_evaluated", True))


def msd_msid_gates(chain: dict) -> dict:
    """Pass-polarity gate entries for the MSD kinetic-trap flag and the MSID Gaussian-chain
    check, computed by check_equilibration_comprehensive.py at chain.msd / chain.msid but
    never previously read by enforce_gate.py -- always advisory (see ALWAYS_ADVISORY)."""
    msd = chain.get("msd", {})
    msid = chain.get("msid", {})
    msd_not_trapped = (not msd["kinetic_trap_flag"]) if "kinetic_trap_flag" in msd else None
    msid_gaussian = msid.get("gaussian_pass") if msid.get("available") else None
    return {"msd_not_trapped": msd_not_trapped, "msid_gaussian": msid_gaussian}


# Gates that a 300K EXTEND can actually fix (not-yet-converged, not structurally wrong).
# n_eff_density belongs here: too few independent samples is undersampling of a valid
# state, and more NPT at the same temperature is exactly the remedy.
EXTENDABLE_GATES = {"density_drift", "energy_drift", "density_sem", "energy_sem",
                    "n_eff_density"}
# Gates whose failure means the cell is WRONG, not merely unconverged -- extending at 300K
# cannot fix these (policy: "a glass cannot densify below Tg").
STRUCTURAL_GATES = {"density_homogeneity", "density_in_band", "p2", "density_value_binding",
                    "finite_size"}


def enforce(run_name, repo_root: Path):
    run_dir = repo_root / "manuscript" / "data" / run_name
    if not run_dir.exists():
        run_dir = repo_root / "data" / run_name
    raw = run_dir / "raw"

    plan = load_json(raw / "run_plan.json")
    comp = load_json(raw / "equilibration_comprehensive.json")
    dens = load_json(raw / "equilibrated_density.json")
    cooling = load_json(raw / "cooling_contraction.json")  # may not exist
    policy = load_json(repo_root / "orchestration" / "decision_policy.json")
    rules = load_json(repo_root / "guides" / "polymer_rules.json")

    if plan is None or comp is None:
        return {"run_name": run_name, "verdict": "UNADJUDICATED",
                "reason": "missing run_plan.json or equilibration_comprehensive.json"}

    dp = plan.get("decided_params", {})
    polymer_class = plan.get("polymer_class", "")
    t_workflow = dp.get("T_workflow_K")
    regime = resolve_regime(t_workflow)

    cls_rules = (rules or {}).get("classes", {}).get(polymer_class, {})
    dp_typical = dp.get("dp_typical") or cls_rules.get("dp_typical")
    ct_gate_reliable = cls_rules.get("ct_gate_reliable")

    # --- pull per-gate pass booleans from equilibration_comprehensive.json ---
    gates = collect_gates(comp)

    # --- density-in-band (density_value_binding target) ---
    exp_density_dict = cls_rules.get("experimental_density_gcm3")
    polymer_key = run_name.rstrip("0123456789")  # e.g. "PMMA2" -> "PMMA"
    # experimental_density_gcm3 keys are member names (e.g. "PMMA"); polymer_key already matches
    plateau_mean = (dens or {}).get("plateau_density_mean")
    in_band, gap_pct, exp_val = density_in_band(plateau_mean, exp_density_dict, polymer_key)
    gates["density_in_band"] = in_band  # may be None if no exp value on file

    # --- determine applicable clause ---
    clause, binding_results, advisory_results = classify(gates, regime, dp_typical, ct_gate_reliable)
    binding_all_pass = all(binding_results.values()) if binding_results else True

    # --- density_value_binding: assess_cooling_contraction must have run if glassy density is >5% low ---
    dvb_status = "n/a"
    if regime == "glassy" and gap_pct is not None and gap_pct < -5.0:
        if cooling is not None and cooling.get("verdict") in (
            "UNDER_ANNEALED_COOLING", "MELT_STAGE_DEFICIT", "OK"
        ):
            dvb_status = f"satisfied ({cooling['verdict']})"
        else:
            dvb_status = "missing_evidence"
            binding_all_pass = False  # density_value_binding is itself binding

    overall_pass_reported = comp.get("overall_pass")
    failing_binding = [k for k, v in binding_results.items() if v is False]
    if dvb_status == "missing_evidence":
        failing_binding.append("density_value_binding")

    # density_value_binding is a policy-level check independent of check_equilibration_comprehensive's
    # own overall_pass (which only tests drift/SEM stability, never absolute magnitude vs experiment) --
    # so it can veto a PASS_CLEAN verdict on its own.
    if not failing_binding and overall_pass_reported is True:
        verdict = "PASS_CLEAN"
    elif binding_all_pass and not failing_binding:
        verdict = "PASS_CARVEOUT"
    else:
        verdict = "VIOLATION"

    # --- D-05 placeholder lint ---
    run_log = run_dir / "run_log.md"
    d05_placeholder = False
    if run_log.exists():
        text = run_log.read_text(errors="ignore")
        if D05_PLACEHOLDER_RE.search(text):
            d05_placeholder = True
            verdict = "UNADJUDICATED"

    return {
        "run_name": run_name,
        "polymer_class": polymer_class,
        "regime": regime,
        "dp_typical": dp_typical,
        "ct_gate_reliable": ct_gate_reliable,
        "applicable_clause": clause,
        "binding_gates": binding_results,
        "advisory_gates": advisory_results,
        "density_gap_pct": round(gap_pct, 2) if gap_pct is not None else None,
        "density_value_binding": dvb_status,
        "overall_pass_reported": overall_pass_reported,
        "failing_binding_gates": failing_binding,
        "d05_placeholder_unfilled": d05_placeholder,
        "verdict": verdict,
    }


def enforce_live(args) -> dict:
    """Live-run gate enforcement for equilibration-checker (Step 3), called via
    `enforce_gate.py --live` with explicit values already present in the worker's
    runtime arguments (regime/dp/exp density/tg from stage_params.py) -- does not depend on
    run_plan.json having been fully written yet.

    Emits a 4-way verdict the orchestrator can route directly:
      PASS            -> equil_verdict=PASS
      EXTEND          -> equil_verdict=EXTEND (re-run at 300K; only drift/SEM gates failed)
      STRUCTURAL_FAIL -> equil_verdict=STRUCTURAL_FAIL (NEW — route to the specific recovery
                         ladder: re-melt+slow-recool for UNDER_ANNEALED_COOLING, heavy-melt-anneal
                         probe for MELT_STAGE_DEFICIT. EXTEND cannot fix these.)
      FAIL            -> equil_verdict=FAIL (unclassifiable / hard structural failure)
    """
    comp = load_json(Path(args.comprehensive_json))
    if comp is None:
        return {"verdict": "FAIL", "reason": f"missing {args.comprehensive_json}"}

    gates = collect_gates(comp)

    regime = args.regime
    dp_typical = args.dp
    ct_gate_reliable = args.ct_gate_reliable

    # --- density-in-band, straight from plateau_density_mean if present in comp's neighbor file ---
    dens_path = Path(args.comprehensive_json).parent / "equilibrated_density.json"
    dens = load_json(dens_path)
    plateau_mean = (dens or {}).get("plateau_density_mean")
    exp_density = args.exp_density_gcm3
    gap_pct = None
    if plateau_mean is not None and exp_density is not None:
        gap_pct = 100.0 * (plateau_mean - exp_density) / exp_density
        gates["density_in_band"] = abs(gap_pct) <= 5.0

    clause, binding_results, advisory_results = classify(gates, regime, dp_typical, ct_gate_reliable)
    failing_binding = [k for k, v in binding_results.items() if v is False]

    # --- density_value_binding: live probe-or-check ---
    dvb_status = "n/a"
    cooling_verdict = None
    cooling_reliable = True
    if regime == "glassy" and gap_pct is not None and gap_pct < -5.0:
        cooling_path = Path(args.out_dir) / "cooling_contraction.json" if args.out_dir else None
        cooling = load_json(cooling_path) if cooling_path else None
        if cooling is not None and cooling.get("verdict") in (
            "UNDER_ANNEALED_COOLING", "MELT_STAGE_DEFICIT", "OK"
        ):
            dvb_status = f"satisfied ({cooling['verdict']})"
            cooling_verdict = cooling.get("verdict")
            cooling_reliable = cooling.get("extrapolation_reliable", True)
        else:
            return {
                "needs_probe": True,
                "reason": f"density {gap_pct:.2f}% below experiment (>5% threshold) — "
                          "density_value_binding requires assess_cooling_contraction before "
                          "any verdict can be issued (policy: a bare force-field-bias claim "
                          "is not sufficient).",
                "assess_cooling_contraction_args": {
                    "glass_data": args.glass_data,
                    "melt_data": args.melt_data,
                    # Stage logs carry the whole NPT plateau; the _out.data files carry one
                    # fluctuating final frame. Derived from the data paths by the stage layout
                    # (<stage>/<stage>_out.data -> <stage>/<stage>.log); assess_cooling_
                    # contraction falls back to the final frame when the log is absent.
                    "glass_log": _stage_log_for(args.glass_data),
                    "melt_log": _stage_log_for(args.melt_data),
                    "exp_density_gcm3": exp_density,
                    "tg_K": args.tg_k,
                    "t_equil_K": args.t_equil_k,
                    # None -> assess_cooling_contraction.py falls back to its own generic
                    # defaults (2.5e-4 / 6.0e-4); only set when the plan curated a class- or
                    # grounding-sourced value (decided_params.alpha_glass_per_K/alpha_melt_per_K).
                    "alpha_glass": getattr(args, "alpha_glass_per_k", None),
                    "alpha_melt": getattr(args, "alpha_melt_per_k", None),
                },
                "save_result_to": str(cooling_path),
            }
        if cooling_verdict != "OK":
            failing_binding.append("density_value_binding")

    # --- 4-way verdict mapping ---
    if not failing_binding:
        verdict = "PASS"
    elif set(failing_binding) <= EXTENDABLE_GATES:
        verdict = "EXTEND"
    elif set(failing_binding) & STRUCTURAL_GATES:
        verdict = "STRUCTURAL_FAIL"
    else:
        verdict = "FAIL"

    remedy = None
    remedy_confidence = "high"
    fs_verdict = finite_size_verdict(comp)
    if verdict == "EXTEND":
        # Size the extension from the deficit rather than a flat 1.5 ns: a run at n_eff=11
        # against a floor of 20 needs ~2x the sampling, not one more nominal nanosecond.
        n_eff = ((comp.get("thermo") or {}).get("n_eff_density") or {}).get("n_eff")
        n_eff_min = ((comp.get("thermo") or {}).get("n_eff_density") or {}).get("n_eff_min", 20)
        if "n_eff_density" in failing_binding and n_eff:
            extend_ns = round(1.5 * max(1.0, n_eff_min / max(n_eff, 1)), 1)
            remedy = (f"extend_only at the SAME temperature: extend_ns={extend_ns} "
                      f"(1.5 x {n_eff_min}/{n_eff} independent-sample deficit). "
                      "phase=full extends npt_prod_data_path at npt_prod_temp_K; phase=melt "
                      "extends npt_production_data_path at T_workflow_K. Cap 2 per gate.")
        else:
            remedy = ("extend_only at the SAME temperature: extend_ns = "
                      "max(1.5, 1.5*ct_tau_relax_ps/1000), else 1.5 ns. Never re-melt a cooled "
                      "glass — phase=full uses npt_prod_temp_K, not T_equil_K. Cap 2 per gate.")
    elif verdict == "STRUCTURAL_FAIL":
        if fs_verdict == "SIZE_MIN_IMAGE_VIOLATION":
            remedy = ("REBUILD LARGER — L < 2*cutoff_A means the pair potential itself is wrong "
                      "(atoms interact with their own images). Raise nchain (or dp) until "
                      "L >= 2*cutoff_A; no re-equilibration of this cell is meaningful.")
        elif fs_verdict == "SIZE_CHAIN_SELF_IMAGE":
            remedy = ("REBUILD LARGER — L < 2*Rg means every chain overlaps its own periodic "
                      "images, biasing packing and therefore density and the moduli. Raise nchain "
                      "(cell volume scales with it at fixed density, so L grows as nchain^(1/3)) "
                      "until L >= 2*Rg. Extending or re-cooling cannot fix a too-small box.")
        elif cooling_verdict == "UNDER_ANNEALED_COOLING":
            remedy = ("re_melt_slow_recool — re-melt from npt_production_out.data at T_equil_K "
                      "(never the 300 K cell) and slow the ramp: npt_cool300_steps and "
                      "npt_cool_steps x2 on attempt 1, x4 on attempt 2 (max 2). Baselines: "
                      "npt_cool300_steps=int(1.0e6/dt_fs); npt_cool_steps from the atom tier "
                      "(<5000->1e6, <15000->2e6, else 3e6). Do NOT extend at 300 K.")
        elif cooling_verdict == "MELT_STAGE_DEFICIT":
            remedy = ("heavy_melt_anneal_probe — re-generate the workflow with add_melt_npt=True, "
                      "t_equil_K=<class T_equil_K>, and melt_npt_steps=10*int(1.0e6/dt_fs) "
                      "(~10 ns hold) on attempt 1, 50x (~50 ns) on attempt 2; re-run the "
                      "phase=melt gate after each. The 1 ns default is ~100x short of the ~100 ns "
                      "melt anneal that reached PMMA 1.19 g/cm3 (NkepsuMbitou 2025). Still "
                      "under-band after rung 2 -> escalate to a different force field.")
        elif "density_homogeneity" in failing_binding:
            remedy = ("MELT-MIXING — extend the melt stage in place (phase=melt extend_only at "
                      "T_workflow_K, cap 2), then re-run the phase=melt gate. Never re-melt from "
                      "scratch and never touch the cooling ramp for a mixing defect.")
        else:
            remedy = "route to RECOVERY — structural gate failure without a specific density_value_binding diagnosis"

        if cooling_verdict in ("UNDER_ANNEALED_COOLING", "MELT_STAGE_DEFICIT") and not cooling_reliable:
            remedy_confidence = "low"
            remedy += (" [LOW CONFIDENCE: cooling span >300K — the alpha-based melt/cooling "
                       "split (UNDER_ANNEALED_COOLING vs MELT_STAGE_DEFICIT) is unreliable here; "
                       "treat this remedy as a starting hypothesis, not a firm diagnosis. Lean on "
                       "the absolute glass-vs-experiment density gap as the trustworthy signal.]")

    return {
        "regime": regime,
        "applicable_clause": clause,
        "binding_gates": binding_results,
        "advisory_gates": advisory_results,
        "density_gap_pct": round(gap_pct, 2) if gap_pct is not None else None,
        "density_value_binding": dvb_status,
        # Structured, not only embedded in the remedy prose: the melt/cooling split is
        # alpha-extrapolated and unreliable past a 300 K span (PKTN 470 K, PSFO 400 K),
        # so a consumer that reports the verdict must be able to read that flag.
        # None means no cooling assessment applied here, NOT "reliable".
        "cooling_verdict": cooling_verdict,
        "cooling_extrapolation_reliable": cooling_reliable if cooling_verdict else None,
        "homogeneity_verdict": ((comp.get("spatial") or {})
                                .get("density_homogeneity", {}).get("verdict")),
        "finite_size_verdict": fs_verdict,
        "finite_size": (comp.get("spatial") or {}).get("finite_size"),
        "finite_size_min_image_unarmed": finite_size_min_image_unarmed(comp),
        "residual_stress": (comp.get("thermo") or {}).get("residual_stress"),
        "failing_binding_gates": failing_binding,
        "verdict": verdict,
        "remedy": remedy,
        "remedy_confidence": remedy_confidence,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_name", nargs="?")
    ap.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--live", action="store_true", help="Live-run mode for equilibration-checker")
    ap.add_argument("--comprehensive-json")
    ap.add_argument("--regime", choices=["glassy", "rubbery"])
    ap.add_argument("--dp", type=lambda v: None if v == "null" else float(v))
    ap.add_argument("--ct-gate-reliable", type=lambda v: v.lower() != "false")
    ap.add_argument("--exp-density-gcm3", type=lambda v: None if v == "null" else float(v))
    ap.add_argument("--tg-k", type=lambda v: None if v == "null" else float(v))
    ap.add_argument("--t-equil-k", type=float)
    ap.add_argument("--glass-data")
    ap.add_argument("--melt-data")
    ap.add_argument("--out-dir")
    ap.add_argument("--alpha-glass-per-k", type=lambda v: None if v == "null" else float(v))
    ap.add_argument("--alpha-melt-per-k", type=lambda v: None if v == "null" else float(v))
    args = ap.parse_args()

    if args.live:
        result = enforce_live(args)
    else:
        if not args.run_name:
            ap.error("run_name required unless --live")
        result = enforce(args.run_name, Path(args.repo_root))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
