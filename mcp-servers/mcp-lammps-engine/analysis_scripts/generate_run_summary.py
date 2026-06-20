#!/usr/bin/env python3
"""
generate_run_summary.py — Aggregate all Stage 4 analysis outputs into a single
canonical run_summary.json that mirrors the run_log.md sections.

Reads all JSON files in output_dir, assembles the summary, fills provenance
from git and version strings already present in analysis JSON outputs, and
writes run_summary.json to output_dir.

Usage:
    python generate_run_summary.py \
        --output_dir /path/to/data/RUN/outputs \
        --run_name PS1 \
        --smiles "*CC(c1ccccc1)*" \
        --polymer_class PSTR \
        --ff TraPPE-UA \
        --simulation_dir /home/alexzhao/simulations/PS1_20260602 \
        [--charge_method "embedded in FF"] \
        [--dp 50] [--n_chains 10] [--n_atoms 5320] \
        [--date_start 2026-06-02] [--date_end 2026-06-03] \
        [--d01 "TraPPE-UA"] [--d02 "embedded in FF"] \
        [--d03 "lj/cut 12 Å"] [--d04 "DP=50, 10 chains, 5320 atoms"] \
        [--d05 "PASS"] [--d06 "ACCEPTABLE"] \
        [--exp_tg_min 370] [--exp_tg_max 380] \
        [--exp_density_min 1.04] [--exp_density_max 1.06]
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def _git_commit(cwd=None):
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=cwd,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    p = argparse.ArgumentParser(description="Aggregate Stage 4 outputs into run_summary.json")
    p.add_argument("--output_dir",      required=True)
    p.add_argument("--run_name",        required=True)
    p.add_argument("--smiles",          default="")
    p.add_argument("--polymer_class",   default="")
    p.add_argument("--ff",              default="")
    p.add_argument("--charge_method",   default="")
    p.add_argument("--simulation_dir",  default="")
    p.add_argument("--dp",              type=int,   default=None)
    p.add_argument("--n_chains",        type=int,   default=None)
    p.add_argument("--n_atoms",         type=int,   default=None)
    p.add_argument("--date_start",      default="")
    p.add_argument("--date_end",        default="")
    # Decision IDs
    p.add_argument("--d01", default=None, help="D-01 Force field choice")
    p.add_argument("--d02", default=None, help="D-02 Charges choice")
    p.add_argument("--d03", default=None, help="D-03 Electrostatics choice")
    p.add_argument("--d04", default=None, help="D-04 System size choice")
    p.add_argument("--d05", default=None, help="D-05 Convergence verdict")
    p.add_argument("--d06", default=None, help="D-06 Tg fit quality")
    # Experimental references
    p.add_argument("--exp_tg_min",      type=float, default=None)
    p.add_argument("--exp_tg_max",      type=float, default=None)
    p.add_argument("--exp_density_min", type=float, default=None)
    p.add_argument("--exp_density_max", type=float, default=None)
    p.add_argument("--exp_K_min",       type=float, default=None)
    p.add_argument("--exp_K_max",       type=float, default=None)
    p.add_argument("--graphs_dir",      default=None,
                   help="Directory where PNG figures were saved (default: <output_dir>/figures/)")
    p.add_argument("--run_plan",        default=None,
                   help="Path to the approved run_plan.json. When given, its structured "
                        "decisions (evidence/confidence/alternatives) and critique are carried "
                        "into the summary, closing the planned→executed→validated loop.")
    p.add_argument("--n_replicates",    type=int, default=None,
                   help="Number of replicates contributing to the multi-rate Tg registry "
                        "(distinct replicate rows). Reported in results.tg for the DSC extrapolation.")
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir = Path(args.graphs_dir) if args.graphs_dir else output_dir / 'figures'

    # -----------------------------------------------------------------------
    # Load all analysis JSON outputs
    # -----------------------------------------------------------------------
    tg           = _load_json(output_dir / "tg_summary.json")
    tg_mr        = _load_json(output_dir / "tg_multirate_result.json")
    eq_dens      = _load_json(output_dir / "equilibrated_density.json")
    eq_chk       = _load_json(output_dir / "equilibration_check.json")
    bulk         = _load_json(output_dir / "bulk_modulus.json")
    bulk_deform  = _load_json(output_dir / "bulk_modulus_deform.json")
    bulk_murnaghan = _load_json(output_dir / "bulk_modulus_murnaghan.json")
    e2e     = _load_json(output_dir / "end_to_end_summary.json")
    rdf     = _load_json(output_dir / "rdf_summary.json")
    rg      = _load_json(output_dir / "rg_summary.json")
    msd     = _load_json(output_dir / "msd_summary.json")
    orient  = _load_json(output_dir / "orientation_summary.json")
    dh      = _load_json(output_dir / "density_summary.json")

    # -----------------------------------------------------------------------
    # Results section
    # -----------------------------------------------------------------------
    Tg_val = tg.get("Tg_K")
    exp_tg = ([args.exp_tg_min, args.exp_tg_max]
              if args.exp_tg_min is not None and args.exp_tg_max is not None else None)
    tg_err = None
    tg_status = "no exp ref"
    if Tg_val is not None and exp_tg:
        exp_mid = (exp_tg[0] + exp_tg[1]) / 2
        tg_err = round(abs(Tg_val - exp_mid) / exp_mid * 100, 1)
        tg_status = "PASS" if exp_tg[0] <= Tg_val <= exp_tg[1] else "FAIL"

    rho_val = eq_dens.get("plateau_density_mean") or eq_dens.get("density_mean")
    exp_rho = ([args.exp_density_min, args.exp_density_max]
               if args.exp_density_min is not None and args.exp_density_max is not None else None)
    rho_err = None
    rho_status = "no exp ref"
    if rho_val is not None and exp_rho:
        exp_mid = (exp_rho[0] + exp_rho[1]) / 2
        rho_err = round(abs(rho_val - exp_mid) / exp_mid * 100, 1)
        rho_status = "PASS" if exp_rho[0] <= rho_val <= exp_rho[1] else "FAIL"

    # K-source precedence: murnaghan > deform > fluctuation
    # Murnaghan is barostat-independent and handles EOS nonlinearity (rubbery).
    # Deform is the authoritative method for glassy polymers.
    # Fluctuation (B_dyn) is a diagnostic fallback.
    if bulk_murnaghan.get("B0_GPa") is not None:
        K_val    = bulk_murnaghan.get("B0_GPa")
        K_sem    = bulk_murnaghan.get("B0_sem_GPa")
        K_method = "murnaghan"
    elif bulk_deform.get("K_GPa") is not None:
        K_val    = bulk_deform.get("K_GPa")
        K_sem    = bulk_deform.get("K_sem_GPa")
        K_method = "deformation"
    else:
        K_val    = bulk.get("bulk_modulus_GPa")
        K_sem    = bulk.get("bulk_modulus_sem_GPa")
        K_method = "fluctuation" if K_val is not None else None

    exp_K = ([args.exp_K_min, args.exp_K_max]
             if args.exp_K_min is not None and args.exp_K_max is not None else None)
    K_status = "no exp ref"
    K_err = None
    if K_val is not None and exp_K:
        exp_mid = (exp_K[0] + exp_K[1]) / 2
        K_err = round(abs(K_val - exp_mid) / exp_mid * 100, 1)
        K_status = "PASS" if exp_K[0] <= K_val <= exp_K[1] else "FAIL"

    # -----------------------------------------------------------------------
    # Artifact pointers (relative to data/[RUN]/)
    # -----------------------------------------------------------------------
    def rel(fname):
        """Return raw/<fname> if file exists, else None."""
        full = output_dir / fname
        return f"raw/{fname}" if full.exists() else None

    def rel_fig(fname):
        full = graphs_dir / fname
        return f"graphs/{fname}" if full.exists() else None

    artifacts = {
        "tg_summary":              rel("tg_summary.json"),
        "tg_density_bins":         rel("tg_density_bins.csv"),
        "tg_fit_fig":              rel_fig("tg_fit.png"),
        "tg_multirate_result":     rel("tg_multirate_result.json"),
        "tg_multirate_d06":        rel("d06_multirate_block.md"),
        "tg_multirate_fig":        rel("tg_multirate.png"),
        "equilibrated_density":    rel("equilibrated_density.json"),
        "equilibration_check":     rel("equilibration_check.json"),
        "equilibration_fig":       rel_fig("equilibration_convergence.png"),
        "bulk_modulus":            rel("bulk_modulus.json"),
        "bulk_modulus_deform":     rel("bulk_modulus_deform.json"),
        "bulk_modulus_murnaghan":  rel("bulk_modulus_murnaghan.json"),
        "volume_timeseries":       rel("volume_timeseries.csv"),
        "volume_fig":              rel_fig("volume_fluctuations.png"),
        "murnaghan_eos_fig":       rel_fig("murnaghan_eos.png"),
        "stress_strain_csv":       rel("stress_strain.csv"),
        "stress_strain_fig":       rel_fig("stress_strain.png"),
        "rdf_summary":             rel("rdf_summary.json"),
        "rdf_fig":                 rel_fig("rdf_all_pairs.png"),
        "end_to_end_summary":      rel("end_to_end_summary.json"),
        "end_to_end_vectors":      rel("end_to_end_vectors.csv"),
        "end_to_end_fig":          rel_fig("end_to_end_distribution.png"),
        "rg_summary":              rel("rg_summary.json"),
        "rg_per_chain":            rel("rg_per_chain.csv"),
        "rg_fig":                  rel_fig("rg_distribution.png"),
        "cn_vs_n":                 rel("cn_vs_n.csv"),
        "cn_vs_n_fig":             rel_fig("cn_vs_n.png"),
        "msd_summary":             rel("msd_summary.json"),
        "msd_chain_com":           rel("msd_chain_com.csv"),
        "msd_fig":                 rel_fig("msd_log.png"),
        "orientation_summary":     rel("orientation_summary.json"),
        "orientation_order":       rel("orientation_order.csv"),
        "orientation_fig":         rel_fig("orientation_p2.png"),
        "density_homogeneity_summary": rel("density_summary.json"),
        "density_homogeneity":     rel("density_homogeneity.csv"),
        "density_homogeneity_fig": rel_fig("density_homogeneity.png"),
    }
    # Drop None entries
    artifacts = {k: v for k, v in artifacts.items() if v is not None}

    # -----------------------------------------------------------------------
    # Plan provenance — carry the approved run_plan.json decisions through
    # -----------------------------------------------------------------------
    plan = _load_json(args.run_plan) if args.run_plan else {}
    if plan:
        artifacts["run_plan"] = "raw/run_plan.json"

    # -----------------------------------------------------------------------
    # Provenance
    # -----------------------------------------------------------------------
    mda_version = (e2e.get("mdanalysis_version") or rg.get("mdanalysis_version")
                   or rdf.get("mdanalysis_version") or "unknown")

    summary = {
        "run": {
            "name":           args.run_name,
            "smiles":         args.smiles,
            "polymer_class":  args.polymer_class,
            "ff":             args.ff,
            "charge_method":  args.charge_method,
            "dp":             args.dp,
            "n_chains":       args.n_chains,
            "n_atoms":        args.n_atoms,
            "date_start":     args.date_start,
            "date_end":       args.date_end,
        },
        "decisions": {
            "D-01_ff":           args.d01,
            "D-02_charges":      args.d02,
            "D-03_electrostatics": args.d03,
            "D-04_system_size":  args.d04,
            "D-05_convergence":  args.d05,
            "D-06_tg_fit_quality": args.d06,
        },
        "plan": {
            "plan_mode":      plan.get("plan_mode"),
            "confidence":     plan.get("confidence"),
            "critique":       plan.get("critique"),
            "uncertainties":  plan.get("uncertainties"),
            # structured decisions with evidence/confidence/alternatives, keyed by id
            "decisions":      {d.get("id"): d for d in plan.get("decisions", [])},
        } if plan else None,
        "results": {
            "tg": {
                "value_K":        Tg_val,
                "exp_range_K":    exp_tg,
                "error_pct":      tg_err,
                "status":         tg_status,
                "r_squared":      tg.get("r_squared"),
                "fit_quality":    tg.get("fit_quality"),
                # Multi-rate DSC extrapolation (log-linear Tg(Γ) → DSC-equivalent rate).
                # tg_dsc_equiv_K is the reported "theoretical DSC-equivalent experimental Tg".
                "tg_dsc_equiv_K":      tg_mr.get("tg_at_slow_rate_K"),
                "loglinear_slope_K":   tg_mr.get("loglinear_slope_K"),
                "loglinear_r_squared": tg_mr.get("loglinear_r_squared"),
                "vf_fit_quality":      tg_mr.get("vf_fit_quality"),
                "n_rates":             tg_mr.get("n_points"),
                "n_replicates":        args.n_replicates,
                "rates_span_decades":  tg_mr.get("rates_span_decades"),
                "slow_rate_ref_K_per_ns": tg_mr.get("slow_rate_ref_K_per_ns"),
            },
            "density": {
                "value_g_cm3":    rho_val,
                "exp_range_g_cm3": exp_rho,
                "error_pct":      rho_err,
                "status":         rho_status,
            },
            "bulk_modulus": {
                "value_GPa":      K_val,
                "sem_GPa":        K_sem,
                "exp_range_GPa":  exp_K,
                "error_pct":      K_err,
                "status":         K_status,
                "method":         K_method,
            },
        },
        "convergence": {
            "verdict":            args.d05,
            "density_equilibrated": eq_chk.get("density_equilibrated"),
            "energy_equilibrated":  eq_chk.get("energy_equilibrated"),
            "density_drift_pct":    (eq_chk.get("density", {}) or {})
                                    .get("drift", {}).get("drift_pct"),
        },
        "structural_checks": {
            "rg_cv":              rg.get("rg_cv_across_chains"),
            "rg_spread_flag":     rg.get("rg_spread_flag"),
            "kinetic_trap_flag":  msd.get("kinetic_trap_flag"),
            "diffusion_regime":   msd.get("diffusion_regime"),
            "ordered_flag":       orient.get("ordered_flag"),
            "p2_mean":            orient.get("p2_mean"),
            "heterogeneous_flag": dh.get("heterogeneous_flag"),
            "density_cv_mean":    dh.get("cv_mean"),
        },
        "artifacts":    artifacts,
        "provenance": {
            "simulation_dir":     args.simulation_dir,
            "git_commit":         _git_commit(cwd=str(output_dir)),
            "mdanalysis_version": mda_version,
            "generated_at":       datetime.now(timezone.utc).isoformat(),
        },
    }

    out_path = output_dir / "run_summary.json"
    with open(out_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Wrote {out_path}", flush=True)
    print(json.dumps({"status": "success", "summary_json": str(out_path)}))


if __name__ == "__main__":
    main()
