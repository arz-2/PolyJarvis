#!/usr/bin/env python3
"""Mechanized D-05 gate-verdict enforcement.

Cross-checks a completed equil run's overall_pass + per-gate results against
decision_policy.json's require_glassy / require_rubbery / plain-require clauses,
programmatically -- not via worker prose. Also applies density_value_binding: an
unconditional, self-consistency-only check (assess_cooling_contraction.py) on whether a
glassy cell's melt->glass density contraction matches its own thermal-expansion prediction.
Never compares to any experimental/curated density or thermal-expansion value -- neither
this gate nor the finite-size forecast reads experimental_density_gcm3/alpha_glass_per_K/
alpha_melt_per_K anymore, so a novel system with none of those curated is assessed exactly
the same way as a well-characterized one.

Usage: python3 enforce_gate.py <run_name> [--repo-root PATH]
Prints a JSON verdict to stdout: PASS_CLEAN | PASS_CARVEOUT | VIOLATION | UNADJUDICATED.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hw_common import resolve_member_value  # noqa: E402  (still used by other callers of this module)

BINDING_GLASSY = {"density_drift", "density_sem", "energy_drift", "energy_sem",
                   "density_homogeneity", "p2", "n_eff_density", "finite_size"}
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


def load_json(path):
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def resolve_regime(final_t_k, tg_k=None):
    """State of the cell at the temperature it is assessed: 'rubbery' iff final_t_k > tg_k.

    final_t_k is the assessment temperature -- check_equilibration_comprehensive always gates
    npt_final, which cool_block ramps down to final_T_K regardless of regime. 300 K is that
    knob's default, never its definition, and it is user-facing.

    Must stay in lockstep with stage_params._regime: this is the retrospective path (enforce),
    that one is the live path (enforce_live receives args.regime already resolved). A divergence
    means the same run is adjudicated two different ways.

    An unresolvable Tg or assessment temperature falls to 'glassy' -- the STRICTER gate set
    (density_drift binds there and is advisory in rubbery), so an unknown must not buy the
    more permissive clause. Callers with no resolvable Tg at all want resolve_regime_legacy."""
    if not isinstance(final_t_k, (int, float)) or not isinstance(tg_k, (int, float)):
        return "glassy"
    return "rubbery" if final_t_k > tg_k else "glassy"


def resolve_regime_legacy(t_workflow_k):
    """The pre-2026-08-31 proxy: 'rubbery' iff T_workflow <= 300 K.

    Kept ONLY for plans that carry no resolvable Tg -- neither a curated member value, a
    frozen decided_params pin, nor a SMILES to match on. It encodes `exp_Tg < 300` indirectly
    via _resolve_t_workflow's own branch, so it is correct exactly while final_T_K is 300 and
    silently misclassifies otherwise. Never use it for new work; prefer resolve_regime."""
    return "rubbery" if t_workflow_k is not None and t_workflow_k <= 300.0 else "glassy"


def _regime_tg_for_plan(plan, cls_rules):
    """This run's Tg for the regime call, or None if nothing can resolve one.

    Prefers a value the plan already froze (an agent override, or the point value
    stage_params resolved at plan time) over re-deriving it here, so the retrospective verdict
    is made against the same number the live run used. Falls back to a scalar class value.
    Deliberately does NOT shell out to the group-contribution estimator: enforce() is an
    offline re-audit and must not depend on the RDKit environment being reachable."""
    dp = plan.get("decided_params", {}) or {}
    for key in ("exp_tg_K", "experimental_tg_K", "exp_tg_point_K"):
        v = dp.get(key)
        if isinstance(v, (int, float)):
            return v
    v = cls_rules.get("experimental_tg_K")
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, dict):
        smiles = plan.get("smiles")
        if smiles:
            try:
                resolved = resolve_member_value(cls_rules, "experimental_tg_K", smiles)
            except Exception:  # noqa: BLE001 -- offline re-audit must not hard-fail on lookup
                resolved = None
            if isinstance(resolved, (int, float)):
                return resolved
    return None


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
    """Pull every per-gate pass boolean out of equilibration.json's thermo/chain/spatial sections.

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
# Gates whose failure means the cell is WRONG, not merely unconverged -- extending at the
# assessment temperature cannot fix these (policy: "a glass cannot densify below Tg").
#
# density_value_binding was a member until 2026-09-01 and is now ADVISORY. It was classified
# Class A on the grounds that its structural remedy (re-melt + slow re-cool) removes the defect
# completely at a bounded one-time cost -- decision_rationale's own "class_A_is_always_worth_paying"
# criterion. Measurement retired that claim. Across 21 archived multi-rate sweeps, glass density
# moves ~1.1% per DECADE of cooling rate, so the slower_cooling remedy (x2 then x4, capped)
# recovers 0.33-0.67% against archived shortfalls of 3-9%: applying the maximum remedy to every
# flagged run clears NONE of them. The gate therefore fails its own class's defining criterion.
#
# The shortfall it measures is real but is not a per-run defect: expected_contraction is built
# from experimental-rate expansivities, and MD cools ~12 decades faster than a DSC scan, so every
# MD glass is legitimately several percent short. That is a Class C agreement statement about an
# inherent MD limitation, not a Class A admissibility failure. Still computed, still reported,
# no longer binding -- see assess_cooling_contraction.assess's alpha-calibration note.
STRUCTURAL_GATES = {"density_homogeneity", "p2", "finite_size"}


def enforce(run_name, repo_root: Path):
    run_dir = repo_root / "manuscript" / "data" / run_name
    if not run_dir.exists():
        run_dir = repo_root / "data" / run_name
    raw = run_dir / "raw"

    plan = load_json(raw / "run_plan.json")
    comp = load_json(raw / "equilibration.json")
    cooling = load_json(raw / "cooling_contraction.json")  # may not exist
    rules = load_json(repo_root / "guides" / "polymer_rules.json")

    if plan is None or comp is None:
        return {"run_name": run_name, "verdict": "UNADJUDICATED",
                "reason": "missing run_plan.json or equilibration.json"}

    dp = plan.get("decided_params", {})
    polymer_class = plan.get("polymer_class", "")
    cls_rules = (rules or {}).get("classes", {}).get(polymer_class, {})

    # Assess against the temperature the cell was actually equilibrated to (final_T_K, whose
    # default is 300 K but which a run may set), compared to this polymer's own Tg. Falls back
    # to the legacy single-argument T_workflow form when no Tg can be resolved -- an old plan
    # with neither a curated member value nor a SMILES to estimate from still adjudicates.
    final_t = dp.get("final_T_K", 300.0)
    tg = _regime_tg_for_plan(plan, cls_rules)
    regime = (resolve_regime(final_t, tg) if tg is not None
              else resolve_regime_legacy(dp.get("T_workflow_K")))

    dp_typical = dp.get("dp_typical") or cls_rules.get("dp_typical")
    ct_gate_reliable = cls_rules.get("ct_gate_reliable")

    # --- pull per-gate pass booleans from equilibration.json ---
    gates = collect_gates(comp)

    # --- determine applicable clause ---
    clause, binding_results, advisory_results = classify(gates, regime, dp_typical, ct_gate_reliable)
    binding_all_pass = all(binding_results.values()) if binding_results else True

    # --- density_value_binding: retrospective, read-only re-audit of a cached
    # cooling_contraction.json (this function never re-runs assess_cooling_contraction --
    # that's enforce_live()'s job during a live run). Binding iff the cached verdict is the
    # new schema's UNDER_ANNEALED_COOLING; a file cached under the OLD (retired) schema
    # (MELT_STAGE_DEFICIT/AMBIGUOUS, from a run equilibrated before this reframing) cannot be
    # honestly re-classified without re-running the script against that run's raw melt/glass
    # data, so it is reported non-binding rather than guessed either way. ---
    dvb_status = "n/a"
    if regime == "glassy":
        if cooling is None:
            dvb_status = "no_cooling_evidence"
        else:
            cooling_verdict = cooling.get("verdict")
            if cooling_verdict == "UNDER_ANNEALED_COOLING":
                # ADVISORY since 2026-09-01 (see STRUCTURAL_GATES): reported, never binding.
                dvb_status = f"satisfied ({cooling_verdict})"
            elif cooling_verdict in ("OK", "INSUFFICIENT_DATA"):
                dvb_status = f"satisfied ({cooling_verdict})"
            else:
                dvb_status = f"stale_verdict_not_reauditable ({cooling_verdict})"

    overall_pass_reported = comp.get("overall_pass")
    failing_binding = [k for k, v in binding_results.items() if v is False]

    if not failing_binding and overall_pass_reported is True:
        verdict = "PASS_CLEAN"
    elif binding_all_pass and not failing_binding:
        verdict = "PASS_CARVEOUT"
    else:
        verdict = "VIOLATION"

    return {
        "run_name": run_name,
        "polymer_class": polymer_class,
        "regime": regime,
        "dp_typical": dp_typical,
        "ct_gate_reliable": ct_gate_reliable,
        "applicable_clause": clause,
        "binding_gates": binding_results,
        "advisory_gates": advisory_results,
        "density_value_binding": dvb_status,
        "overall_pass_reported": overall_pass_reported,
        "failing_binding_gates": failing_binding,
        "verdict": verdict,
    }


def enforce_live(args) -> dict:
    """Live-run gate enforcement for equilibration-checker (Step 3), called via
    `enforce_gate.py --live` with explicit values already present in the worker's
    runtime arguments (regime/dp from stage_params.py) -- does not depend on
    run_plan.json having been fully written yet.

    Emits a 4-way verdict the orchestrator can route directly:
      PASS            -> equil_verdict=PASS
      EXTEND          -> equil_verdict=EXTEND (re-run at 300K; only drift/SEM gates failed)
      STRUCTURAL_FAIL -> equil_verdict=STRUCTURAL_FAIL (NEW — route to the specific recovery
                         ladder: re-melt+slow-recool for UNDER_ANNEALED_COOLING. EXTEND cannot
                         fix these.)
      FAIL            -> equil_verdict=FAIL (unclassifiable / hard structural failure)
    """
    comp = load_json(Path(args.comprehensive_json))
    if comp is None:
        return {"verdict": "FAIL", "reason": f"missing {args.comprehensive_json}"}

    gates = collect_gates(comp)

    regime = args.regime
    dp_typical = args.dp
    ct_gate_reliable = args.ct_gate_reliable

    clause, binding_results, advisory_results = classify(gates, regime, dp_typical, ct_gate_reliable)
    failing_binding = [k for k, v in binding_results.items() if v is False]

    # --- density_value_binding: unconditional self-consistency check (live probe-or-check).
    # Triggers on data-path presence, NOT on any density-vs-experiment gap -- the live
    # checkpoint call at phase=melt legitimately has glass_data/melt_data as None (no
    # post-cool glass state exists yet), so guarding on regime alone would misfire needs_probe
    # there. ---
    dvb_status = "n/a"
    cooling_verdict = None
    cooling_reliable = True
    if regime == "glassy" and args.glass_data and args.melt_data:
        cooling_path = Path(args.out_dir) / "cooling_contraction.json" if args.out_dir else None
        cooling = load_json(cooling_path) if cooling_path else None
        if cooling is not None and cooling.get("verdict") in (
            "UNDER_ANNEALED_COOLING", "OK", "INSUFFICIENT_DATA"
        ):
            dvb_status = f"satisfied ({cooling['verdict']})"
            cooling_verdict = cooling.get("verdict")
            cooling_reliable = cooling.get("extrapolation_reliable", True)
        else:
            return {
                "needs_probe": True,
                "reason": "density_value_binding requires assess_cooling_contraction (a "
                          "self-consistency check on the melt->glass contraction vs. this "
                          "system's own thermal-expansion prediction) before any verdict can "
                          "be issued.",
                "assess_cooling_contraction_args": {
                    "glass_data": args.glass_data,
                    "melt_data": args.melt_data,
                    "glass_log": _stage_log_for(args.glass_data),
                    "melt_log": _stage_log_for(args.melt_data),
                    "tg_K": args.tg_k,
                    "t_equil_K": args.t_equil_k,
                    # The cold endpoint of the contraction is where npt_final actually ran,
                    # not a hardcoded 300 -- see assess_cooling_contraction.assess.
                    "final_T_K": getattr(args, "final_t_k", None) or 300.0,
                },
                "save_result_to": str(cooling_path),
            }
        # ADVISORY since 2026-09-01 -- see STRUCTURAL_GATES. The verdict, the shortfall and
        # its alpha band stay in the gate payload (cooling_verdict below) for the report and for
        # the recovery agent's context; they simply no longer fail the stage.

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
            remedy = (f"extend_only=True, base_stage_name='npt_final', extend_ensemble='npt': "
                      f"extend_ns={extend_ns} (1.5 x {n_eff_min}/{n_eff} independent-sample "
                      "deficit) via restart-continuation (read_restart from npt_final's own "
                      ".restart output, appended log/dump) at npt_prod_temp_K. Cap 2 per gate.")
        else:
            remedy = ("extend_only=True, base_stage_name='npt_final', extend_ensemble='npt': "
                      "extend_ns = max(1.5, 1.5*ct_tau_relax_ps/1000), else 1.5 ns, via "
                      "restart-continuation at npt_prod_temp_K (npt_final always runs at "
                      "final_T_K, default 300 K — never a re-melt). Cap 2 per gate.")
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
            remedy = ("slower_cooling (workflow_engine._cooling) — regenerate the entire "
                      "blockwise cool_block ramp (max_temp -> final_T_K) from the anneal_hold "
                      "checkpoint (equilibration_resume_from='anneal_hold'), doubling "
                      "cool_block_hold_steps per attempt (x2 on attempt 1, x4 on attempt 2, "
                      "max 2). cool_block is the sole stage sequence that crosses Tg in this "
                      "design — there is no separate npt_cool300 stage to target. Do NOT "
                      "extend npt_final at final_T_K.")
        elif "density_homogeneity" in failing_binding:
            remedy = ("MELT-MIXING — extend the melt reference block in place "
                      "(extend_only=True, base_stage_name=<the cool_block_NN tagged as the "
                      "melt reference>, extend_temp_K=temp, cap 2), then re-run the gate. "
                      "Never re-melt from scratch and never touch the cooling ramp for a "
                      "mixing defect.")
        else:
            remedy = "route to RECOVERY — structural gate failure without a specific density_value_binding diagnosis"

        if cooling_verdict == "UNDER_ANNEALED_COOLING" and not cooling_reliable:
            remedy_confidence = "low"
            remedy += (" [LOW CONFIDENCE: cooling span >300K — the alpha-based melt/cooling "
                       "contraction prediction is unreliable here; treat this remedy as a "
                       "starting hypothesis, not a firm diagnosis.]")

    return {
        "regime": regime,
        "applicable_clause": clause,
        "binding_gates": binding_results,
        "advisory_gates": advisory_results,
        "density_value_binding": dvb_status,
        # Structured, not only embedded in the remedy prose: the alpha-based contraction
        # prediction is unreliable past a 300 K cooling span (PKTN 470 K, PSFO 400 K), so a
        # consumer that reports the verdict must be able to read that flag.
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
    ap.add_argument("--tg-k", type=lambda v: None if v == "null" else float(v))
    ap.add_argument("--t-equil-k", type=float)
    ap.add_argument("--glass-data")
    ap.add_argument("--melt-data")
    ap.add_argument("--out-dir")
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
