#!/usr/bin/env python3
"""
generate_run_summary.py — Aggregate all Stage 4 analysis outputs into a single
canonical run_summary.json that mirrors the run_log.md sections.

Reads all JSON files in output_dir, assembles the summary, fills provenance
from git and version strings already present in analysis JSON outputs, and
writes run_summary.json to output_dir. Only tg_summary.json is searched
recursively; anything else an extractor wrote into a subdirectory is reported
in artifacts_missing rather than silently dropped.

Usage:
    python generate_run_summary.py \
        --output_dir /path/to/data/RUN/raw \
        --run_name PS1 \
        --smiles "*CC(c1ccccc1)*" \
        --polymer_class PSTR \
        --ff TraPPE-UA \
        --simulation_dir data/PS1/lammps \
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
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


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


def _dig(d, *keys, default=None):
    """Walk a nested dict by keys, returning default if any level is missing."""
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _not(v):
    """Boolean negation that preserves None (unknown stays unknown)."""
    return (not v) if v is not None else None


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
    p.add_argument("--tg_fox_flory_K", type=float, default=None,
                   help="Flory-Fox K (K*g/mol) from polymer_rules.json tg_fox_flory_K. Shifts the "
                        "EXPERIMENTAL Tg band down to the cell's finite Mn = dp * M_repeat. Omit "
                        "when the class has no citable K — the band is then graded uncorrected.")
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
    p.add_argument("--tg_path",         default=None,
                   help="Explicit path to the canonical tg_summary.json (e.g. the slowest-rate "
                        "folder). When supplied, skips rglob discovery and uses this file directly. "
                        "Prevents alphabetical-order bugs when multiple rate folders coexist.")
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    graphs_dir = Path(args.graphs_dir) if args.graphs_dir else output_dir / 'figures'

    # -----------------------------------------------------------------------
    # Load all analysis JSON outputs
    # -----------------------------------------------------------------------
    artifacts_missing = []

    def _load(name):
        """Load output_dir/<name>, recording anything that did not load. _load_json returns {}
        for missing, malformed and unreadable alike, so without this every gap reads as "the
        analysis produced nothing". `found_in` separates the two cases that matter: a file an
        extractor wrote into a subdirectory (stranded, never read) from one that was never
        produced at all."""
        path = output_dir / name
        if path.exists():
            return _load_json(path)
        stray = next(iter(sorted(output_dir.rglob(name))), None)
        artifacts_missing.append({
            "file": name,
            "found_in": str(stray.relative_to(output_dir)) if stray else None,
        })
        return {}

    tg           = _load("tg_summary.json")
    tg_mr        = _load("tg_multirate_result.json")
    eq_dens      = _load("equilibrated_density.json")
    eq_chk       = _load("equilibration_check.json")
    # check_equilibration_comprehensive actually writes equilibration_comprehensive.json
    # with a nested schema (thermo.*/chain.*/spatial.*); prefer it when present.
    eq_comp      = _load("equilibration_comprehensive.json")
    bulk         = _load("bulk_modulus.json")
    bulk_deform  = _load("bulk_modulus_deform.json")
    bulk_murnaghan = _load("bulk_modulus_murnaghan.json")
    e2e     = _load("end_to_end_summary.json")
    rdf     = _load("rdf_summary.json")
    rg      = _load("rg_summary.json")
    msd     = _load("msd_summary.json")
    orient  = _load("orientation_summary.json")
    dh      = _load("density_summary.json")

    # -----------------------------------------------------------------------
    # Results section
    # -----------------------------------------------------------------------
    # Tg resolution: prefer the rate-extrapolated value (cooling-rate bias removed) over the raw
    # single-rate MD Tg. Multi-rate runs may write per-rate tg_summary.json into subdirs, so search
    # recursively when the top-level file is absent (else Tg silently drops from the summary).
    tg_extrap = (tg_mr or {}).get("tg_at_slow_rate_K")
    try:
        tg_extrap = float(tg_extrap)
        if not math.isfinite(tg_extrap):
            tg_extrap = None
    except (TypeError, ValueError):
        tg_extrap = None
    Tg_raw = tg.get("Tg_K")
    if Tg_raw is None and not tg:
        # Explicit canonical path wins over rglob to avoid alphabetical-order bugs
        # (tg_r160/ sorts before tg_r40/, picking the wrong faster-rate Tg as headline).
        if getattr(args, "tg_path", None) and Path(args.tg_path).exists():
            j = _load_json(Path(args.tg_path))
            if j.get("Tg_K") is not None:
                tg, Tg_raw = j, j.get("Tg_K")
        else:
            for cand in sorted(output_dir.rglob("tg_summary.json")):
                j = _load_json(cand)
                if j.get("Tg_K") is not None:
                    tg, Tg_raw = j, j.get("Tg_K")
                    break
        if tg:
            # Recovered from a per-rate subdir — the only artifact with its own discovery, so it
            # is not stranded and does not belong in artifacts_missing.
            artifacts_missing[:] = [m for m in artifacts_missing if m["file"] != "tg_summary.json"]

    Tg_val = tg_extrap if tg_extrap is not None else Tg_raw
    tg_basis = ("rate_extrapolated" if tg_extrap is not None
                else ("raw_MD" if Tg_raw is not None else None))
    # Fit-quality fields for the results dict: per-rate bilinear r²/quality for a raw single-rate
    # headline, or the multirate log-linear r² when the rate-extrapolated value is reported.
    tg_r2 = tg.get("r_squared")
    tg_quality = tg.get("fit_quality")
    if tg_extrap is not None:
        tg_r2 = tg_mr.get("loglinear_r_squared")
        # Per-rate bilinear fit quality (the D-06 metric) lives in any tg_r*/tg_summary.json.
        for sub in sorted(output_dir.glob("tg_r*/tg_summary.json")):
            tg_quality = _load_json(sub).get("fit_quality")
            break
    def _floor_band(band, *, min_abs=None, min_rel=None):
        """Widen a too-narrow exp band symmetrically to a physical minimum width, so a
        degenerate/single-point or hand-entered tight band can't cause a false FAIL
        (PVC2 0.07% density; PSU4 0.1 K Tg). The floor is set BELOW MD/FF systematic
        error, so it can never mask a genuine method failure. Returns (band, widened)."""
        if not band or band[0] is None or band[1] is None:
            return band, False
        lo, hi = float(band[0]), float(band[1])
        mid = 0.5 * (lo + hi)
        floor = max(min_abs or 0.0, (min_rel or 0.0) * abs(mid))
        if (hi - lo) >= floor or floor <= 0:
            return [lo, hi], False
        r = floor / 2.0
        return [round(mid - r, 4), round(mid + r, 4)], True

    def _repeat_unit_mass(smiles):
        """Molar mass of one repeat unit, from the * -terminated repeat SMILES.

        Reuses estimate_tg_group_contribution._prepare_repeat_unit rather than calling
        MolWt on the raw string: * carries no mass but leaves the H count on every
        wildcard-adjacent atom one too high, turning each backbone CH2 into a CH3."""
        if not smiles:
            return None
        try:
            # Probe RDKit FIRST. estimate_tg_group_contribution calls sys.exit() at import
            # when RDKit is missing, which prints its own error JSON to stdout and raises
            # SystemExit -- neither is catchable as an ordinary import failure here.
            from rdkit.Chem import Descriptors
        except ImportError:
            return None
        try:
            sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))
            from estimate_tg_group_contribution import _prepare_repeat_unit
            mol = _prepare_repeat_unit(smiles)
            return float(Descriptors.MolWt(mol)) if mol is not None else None
        except Exception:
            return None

    def _dp_correction(K, dp, smiles):
        """Flory-Fox shift of the EXPERIMENTAL band to the cell's finite Mn.

        Tg(Mn) = Tg_inf - K/Mn, so the correction is negative and the band moves DOWN,
        toward the simulated value. That direction is the same one md_offset_K moved in,
        and the distinction is the whole justification for allowing it here: md_offset_K
        corrected the SIMULATION for a method artifact (cooling rate), which manufactures a
        PASS by discarding the discrepancy the grade exists to report. This corrects the
        REFERENCE for molecular weight -- a handbook Tg is a high-MW plateau value and a
        dp=40 cell has a genuinely different true Tg, so the comparison is otherwise not
        like-for-like. Fox & Flory put the plateau near Mn ~30,000, an order of magnitude
        above what this campaign builds.

        Returns (correction_K, reason_when_absent, Mn). Any missing input yields
        (None, reason, Mn-or-None) and the band is graded UNCORRECTED -- never a generic K.
        """
        mn = None
        if K is None:
            return None, "no citable tg_fox_flory_K for this class", None
        if not dp:
            return None, "dp unavailable", None
        m_repeat = _repeat_unit_mass(smiles)
        if not m_repeat:
            return None, "repeat-unit mass unavailable (no SMILES or RDKit)", None
        mn = dp * m_repeat
        return -K / mn, None, round(mn, 1)

    exp_tg = ([args.exp_tg_min, args.exp_tg_max]
              if args.exp_tg_min is not None and args.exp_tg_max is not None else None)
    exp_tg_uncorrected = list(exp_tg) if exp_tg else None
    dp_correction_K, dp_correction_reason, tg_mn = _dp_correction(
        args.tg_fox_flory_K, args.dp, args.smiles)
    if exp_tg and dp_correction_K is not None:
        exp_tg = [round(exp_tg[0] + dp_correction_K, 1),
                  round(exp_tg[1] + dp_correction_K, 1)]
    exp_tg, tg_band_widened = _floor_band(exp_tg, min_abs=10.0)   # >=10 K total (+/-5 K)
    tg_err = None
    tg_status = "no exp ref"
    # Fit uncertainty applies to the raw bilinear breakpoint only. A rate-extrapolated Tg
    # is a log-linear extrapolation across rates and carries no cf_result sigma, so it is
    # graded as a point -- null is not zero, and must not be read as a tight interval.
    tg_interval_half_K = (tg.get("tg_interval_half_width_K")
                          if tg_basis == "raw_MD" else None)
    # extract_thermal's own admissibility verdict. TG_REVIEW/TG_NOT_REPORTABLE means the
    # transition was never localized -- two admissible fits disagreeing, or a sweep that
    # resolved no crossover -- so the distance from an experimental band is not a
    # measurement of anything. Grading it anyway produced a clean-looking FAIL with an
    # error_pct on PMMA1, which the orchestrator then had to overwrite by hand in run_log.
    # A rate-extrapolated headline is graded on its own basis; the per-rate verdict below
    # it does not gate it.
    tg_gate_verdict = tg.get("tg_gate_verdict")
    tg_not_reportable = (tg_basis == "raw_MD" and tg.get("tg_reportable") is False)
    if tg_not_reportable:
        tg_status = f"NOT_GRADED ({tg_gate_verdict or 'tg_reportable=false'})"
    elif Tg_val is not None and exp_tg:
        # Grade the raw value against the REAL exp band, always. A raw single-rate MD Tg
        # overestimates experiment by ~80-120 K (cooling-rate artifact, Patrone 2016), but a
        # METHOD offset must NEVER be folded into the PASS/FAIL band: moving the measured
        # value toward the reference manufactures a PASS, and a prior PLA run did exactly
        # that (feedback_pla_glassy_md_offset_gamed_pass.md). The rate-extrapolated Tg
        # already removes the bias by construction; the raw single-rate Tg is graded exactly
        # as strictly, and the discrepancy is the finding, not something to correct away.
        # Three-valued, not a widened band. _floor_band has already widened the band once,
        # so widening BOTH sides and testing containment would compound into a laundered
        # PASS. Instead the overlap gets its own status, and error_pct keeps the POINT
        # distance to the nearest edge -- zeroing it as PASS does would drop the number
        # that makes the annotation readable.
        lo, hi = exp_tg[0], exp_tg[1]
        if lo <= Tg_val <= hi:
            tg_status, tg_err = "PASS", 0.0
        else:
            nearest = lo if Tg_val < lo else hi
            tg_err = round((Tg_val - nearest) / nearest * 100, 1)
            half = tg_interval_half_K
            overlaps = (half is not None and half > 0
                        and Tg_val + half >= lo and Tg_val - half <= hi)
            tg_status = "PASS_WITHIN_UNCERTAINTY" if overlaps else "FAIL"

    rho_val = eq_dens.get("plateau_density_mean") or eq_dens.get("density_mean")
    exp_rho = ([args.exp_density_min, args.exp_density_max]
               if args.exp_density_min is not None and args.exp_density_max is not None else None)
    exp_rho_supplied = list(exp_rho) if exp_rho else None
    exp_rho, rho_band_widened = _floor_band(exp_rho, min_rel=0.06)   # >=6% total (+/-3%)
    rho_err = None
    rho_status = "no exp ref"
    if rho_val is not None and exp_rho:
        rho_status = "PASS" if exp_rho[0] <= rho_val <= exp_rho[1] else "FAIL"
        if rho_status == "PASS":
            rho_err = 0.0
        else:
            nearest = exp_rho[0] if rho_val < exp_rho[0] else exp_rho[1]
            rho_err = round((rho_val - nearest) / nearest * 100, 1)

    # K-source precedence: murnaghan > deform > fluctuation
    # Murnaghan is the primary glassy (300 K) and rubbery (T>Tg) method.
    # Deform (3-direction) is the fallback when Murnaghan EOS fails.
    # Born+NVT has been removed (PCFF+PPPM virial incompatibility, 2026-06-21).
    # Fluctuation (B_dyn) is a diagnostic cross-check for rubbery systems.
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
    exp_K_supplied = list(exp_K) if exp_K else None
    exp_K, K_band_widened = _floor_band(exp_K, min_rel=0.20)   # >=20% total (+/-10%)
    K_status = "no exp ref"
    K_err = None
    if K_val is not None and exp_K:
        K_status = "PASS" if exp_K[0] <= K_val <= exp_K[1] else "FAIL"
        if K_status == "PASS":
            K_err = 0.0
        else:
            nearest = exp_K[0] if K_val < exp_K[0] else exp_K[1]
            K_err = round((K_val - nearest) / nearest * 100, 1)

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
        "equilibration_comprehensive": rel("equilibration_comprehensive.json"),
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
                "grading_basis":  tg_basis,   # rate_extrapolated | raw_MD — both graded strictly, no offset in the band
                "exp_range_K":    exp_tg,
                # The raw handbook band, always emitted beside the graded one, so a shift is
                # never invisible. Equal to exp_range_K when no correction applied.
                "exp_range_K_uncorrected": exp_tg_uncorrected,
                # Flory-Fox shift of the REFERENCE to the cell's finite Mn (negative K).
                # Null + a reason means the band was graded UNCORRECTED — never that a
                # generic K was substituted.
                "dp_correction_K":        (round(dp_correction_K, 1)
                                           if dp_correction_K is not None else None),
                "dp_correction_reason":   dp_correction_reason,
                "dp_correction_Mn_g_per_mol": tg_mn,
                "band_widened":   tg_band_widened,
                "error_pct":      tg_err,
                # PASS | PASS_WITHIN_UNCERTAINTY | FAIL | no exp ref.
                # PASS_WITHIN_UNCERTAINTY means the POINT sits outside the band but the fit
                # interval overlaps it — a distinct outcome, not a PASS. error_pct still
                # carries the point distance to the nearest edge.
                "status":         tg_status,
                # extract_thermal's admissibility verdict, carried through so a reader never
                # has to open tg_summary.json to find out the value was not gradeable.
                "tg_gate_verdict": tg_gate_verdict,
                "tg_reportable":   tg.get("tg_reportable"),
                # Half-width of the graded interval (K). Null on a rate-extrapolated Tg,
                # which has no breakpoint sigma and is graded as a point.
                "tg_interval_half_width_K": tg_interval_half_K,
                "r_squared":      tg_r2,
                "fit_quality":    tg_quality,
                # True when the headline raw-MD fit still violates a hard physics constraint
                # (no valid alternative existed to swap in, per extract_thermal). Surfaced so the
                # headline Tg is not graded silently — treat the value as unreliable when set.
                "primary_fit_invalid": (tg.get("primary_fit_invalid", False)
                                        if tg_basis == "raw_MD" else False),
                # Multi-rate DSC extrapolation (log-linear Tg(Γ) → DSC-equivalent rate).
                # tg_dsc_equiv_K is the reported "theoretical DSC-equivalent experimental Tg".
                "tg_dsc_equiv_K":      tg_mr.get("tg_at_slow_rate_K"),
                "loglinear_slope_K":   tg_mr.get("loglinear_slope_K"),
                # Per e-fold above; the per-decade value is the one to grade against the
                # 3-5 K/decade physical expectation. Older artifacts lack it -> None.
                "loglinear_slope_K_per_decade": tg_mr.get("loglinear_slope_K_per_decade"),
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
                # The band as passed in. _floor_band widens a too-narrow band to a physical
                # minimum, which also overrides a deliberately tight operator band (cis-PBD1:
                # +/-5% supplied, +/-10% graded), so band_widened alone does not tell the
                # reader what was asked for. Equal to exp_range when nothing was widened.
                "exp_range_g_cm3_supplied": exp_rho_supplied,
                "band_widened":   rho_band_widened,
                "error_pct":      rho_err,
                "status":         rho_status,
            },
            "bulk_modulus": {
                "value_GPa":      K_val,
                "sem_GPa":        K_sem,
                "exp_range_GPa":  exp_K,
                "exp_range_GPa_supplied": exp_K_supplied,
                "band_widened":   K_band_widened,
                "error_pct":      K_err,
                "status":         K_status,
                "method":         K_method,
            },
        },
        "convergence": {
            "verdict":            args.d05 or (("PASS" if eq_comp.get("overall_pass") else "FAIL")
                                              if eq_comp else None),
            # Prefer the comprehensive nested schema; fall back to the legacy flat keys.
            "density_equilibrated": _dig(eq_comp, "thermo", "density_drift", "pass",
                                         default=eq_chk.get("density_equilibrated")),
            "energy_equilibrated":  _dig(eq_comp, "thermo", "energy_drift", "pass",
                                         default=eq_chk.get("energy_equilibrated")),
            "density_drift_pct":    _dig(eq_comp, "thermo", "density_drift", "drift_pct",
                                         default=_dig(eq_chk, "density", "drift", "drift_pct")),
        },
        "structural_checks": {
            "rg_cv":              _dig(eq_comp, "chain", "rg", "cv",
                                       default=rg.get("rg_cv_across_chains")),
            "rg_spread_flag":     (_not(_dig(eq_comp, "chain", "rg", "pass"))
                                   if eq_comp else rg.get("rg_spread_flag")),
            "kinetic_trap_flag":  _dig(eq_comp, "chain", "msd", "kinetic_trap_flag",
                                       default=msd.get("kinetic_trap_flag")),
            "diffusion_regime":   _dig(eq_comp, "chain", "msd", "diffusion_regime",
                                       default=msd.get("diffusion_regime")),
            "ordered_flag":       (_not(_dig(eq_comp, "spatial", "p2", "pass"))
                                   if eq_comp else orient.get("ordered_flag")),
            "p2_mean":            _dig(eq_comp, "spatial", "p2", "p2_mean",
                                       default=orient.get("p2_mean")),
            "heterogeneous_flag": (_not(_dig(eq_comp, "spatial", "density_homogeneity", "pass"))
                                   if eq_comp else dh.get("heterogeneous_flag")),
            "density_cv_mean":    _dig(eq_comp, "spatial", "density_homogeneity", "cv_mean",
                                       default=dh.get("cv_mean")),
        },
        "artifacts":    artifacts,
        "artifacts_missing": artifacts_missing,
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
    for m in artifacts_missing:
        if m["found_in"]:
            print(f"  WARNING: {m['file']} is in {m['found_in']}, not {output_dir} — "
                  f"not read into this summary", flush=True)
    print(json.dumps({"status": "success", "summary_json": str(out_path),
                      "artifacts_missing": artifacts_missing}))


if __name__ == "__main__":
    main()
