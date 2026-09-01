#!/usr/bin/env python3
"""
generate_run_summary.py — Aggregate all Stage 4 analysis outputs into a single
canonical run_summary.json.

Reads all JSON files in output_dir, assembles the summary, fills provenance
from git and version strings already present in analysis JSON outputs, and
writes run_summary.json to output_dir. Only thermal.json is searched
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
        [--d05 "PASS"] [--d06 "ACCEPTABLE"]

Reports measured values only -- no experimental comparison. Most runs are novel systems with no
curated experimental reference, so a PASS/FAIL grading column would be blank far more often than
not; compare a run's results.tg/density/bulk_modulus values against literature by hand (or via
exp_lookup.json, written separately for provenance) when a reference happens to exist.
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


def _collect_byproducts(spec_path, loaded):
    """Surface free measurements with their own gate verdicts. Never raises: a byproduct that
    cannot be read is simply absent, because nothing here may affect the run's own verdict."""
    if not spec_path:
        return {}
    try:
        spec = json.loads(Path(spec_path).read_text())
    except Exception:
        return {}
    out = {}
    for entry in spec if isinstance(spec, list) else []:
        source = loaded.get(entry.get("source_json"))
        if not isinstance(source, dict):
            continue
        value = source.get(entry.get("field"))
        if value is None:
            continue
        gate_field = entry.get("gate_field")
        verdict = source.get(gate_field) if gate_field else None
        out[entry["name"]] = {
            "value": value,
            "unit": entry.get("unit") or "",
            "produced_by": entry.get("produced_by"),
            "track": entry.get("track"),
            "source": f"{entry.get('source_json')}:{entry.get('field')}",
            "gate": {"field": gate_field, "verdict": verdict},
            "blocking": False,
        }
    return out


def _convergence_caveats(eq_comp):
    """Surface accepted-but-suspect chain-relaxation conditions that convergence.verdict alone
    hides. kinetic_trap_flag/ct/msid_gaussian are deliberately advisory (never gated), per
    enforce_gate.py's ALWAYS_ADVISORY set and decision_policy.json's documented rationale (full
    chain relaxation is often unattainable within MD timescales for rubbery/high-DP systems, so
    binding on it would make overall_pass unsatisfiable by construction) -- but "advisory" should
    not mean "invisible". Without this, a reader sees convergence.verdict=PASS and would have to
    separately notice structural_checks fields (a different section) to connect the two.
    """
    caveats = []

    # kinetic_trap_flag/C(t): only meaningful in the rubbery/melt regime. Below Tg, limited chain
    # diffusion is EXPECTED (chains are arrested by design), not a red flag -- see PEG1's own
    # warning text, "expected below Tg, problematic in melt state." A glassy run's own
    # kinetic_trap_flag=True is therefore NOT surfaced.
    if _dig(eq_comp, "gate", "regime") == "rubbery":
        if _dig(eq_comp, "chain", "msd", "kinetic_trap_flag") is True:
            regime_note = _dig(eq_comp, "chain", "msd", "diffusion_regime") or "sub-diffusive"
            caveats.append(
                f"kinetic_trap_flag=True ({regime_note}) in a rubbery/melt run -- chains have not "
                "displaced their own size (MSD_max < Rg^2). density/Tg/bulk_modulus were measured on "
                "a structure whose chain-scale conformation may not represent true equilibrium."
            )
        ct_decay = _dig(eq_comp, "chain", "ct", "decay_fraction_at_end")
        if ct_decay is not None and ct_decay < 0.1:
            tau = _dig(eq_comp, "chain", "ct", "tau_relax_ps")
            traj = _dig(eq_comp, "chain", "ct", "trajectory_ps")
            gap_note = f" (tau_relax={tau:.3g} ps vs trajectory={traj:.0f} ps)" if tau and traj else ""
            caveats.append(
                f"C(t) only {ct_decay * 100:.0f}% decayed by end of trajectory{gap_note} -- "
                "whole-chain conformational relaxation is far from complete."
            )

    # GLOBAL_CHAIN_CONFIGURATION_NOT_RELAXED (Auhl et al., cond-mat/0306026): a large-s MSID
    # distortion riding on top of otherwise-healthy small/intermediate-s statistics -- the
    # signature of a long-wavelength chain conformation that was never correct (most likely
    # inherited from the build) and that ordinary MD, bounded by reachable timescales, cannot
    # repair. Named/anticipated in check_equilibration_comprehensive.py's own MSID regime-split
    # code and test_msid_regime_split.py, but never actually wired into a visible signal until
    # now. Unlike kinetic_trap_flag, this is NOT regime-gated: a glassy run's conformation is
    # whatever the melt phase produced before cooling froze it in, so the defect (if present)
    # matters just as much there -- arguably more, since cooling can never fix it either.
    large_s = _dig(eq_comp, "chain", "msid", "large_s")
    if large_s and large_s.get("gaussian_pass") is False:
        slope = large_s.get("slope")
        s_range = large_s.get("s_range")
        s_note = f" (s={s_range[0]}-{s_range[1]})" if s_range else ""
        caveats.append(
            f"GLOBAL_CHAIN_CONFIGURATION_NOT_RELAXED: large-s MSID slope={slope}{s_note}, "
            "expected 1.0 +/-20% for melt-screened (ideal-chain) statistics -- long-wavelength "
            "chain shape has not relaxed to equilibrium. Local packing/short-range structure can "
            "still be sound; whole-chain conformation may not represent true equilibrium."
        )

    # anneal_hold_msid_gate (opt-in, per-class): the gate stopped without confirming large-s
    # MSID actually converged -- either its extension cap was reached first (EXHAUSTED) or an
    # extension run itself crashed (EXTENSION_FAILED, PROBE_FAILED). Advisory, same as the
    # GLOBAL_CHAIN_CONFIGURATION_NOT_RELAXED caveat above -- cool_block_01 still ran from
    # whatever anneal_hold data existed at that point, not a hard failure.
    ahc = eq_comp.get("anneal_hold_convergence") if isinstance(eq_comp, dict) else None
    if ahc and ahc.get("outcome") in ("EXHAUSTED", "EXTENSION_FAILED", "PROBE_FAILED"):
        slope_history = ahc.get("slope_history") or []
        last_slope = slope_history[-1] if slope_history else None
        caveats.append(
            f"ANNEAL_HOLD_MSID_GATE_{ahc['outcome']}: the anneal_hold MSID-convergence gate "
            f"stopped after {ahc.get('extensions_used', 0)} extension(s) "
            f"({ahc.get('cumulative_hold_ns', '?')} ns cumulative hold) without confirming "
            f"large-s MSID reached the +-20% gaussian_pass band (last measured slope="
            f"{last_slope}). Cooling proceeded from anneal_hold's best available structure "
            "rather than a confirmed-converged one."
        )
    return caveats


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
                   help="Explicit path to the canonical thermal.json (e.g. the slowest-rate "
                        "folder). When supplied, skips rglob discovery and uses this file directly. "
                        "Prevents alphabetical-order bugs when multiple rate folders coexist.")
    p.add_argument("--equilibration_path", default=None,
                   help="Explicit path to the accepted equilibration attempt's equilibration.json. "
                        "Under the attempt-based run layout this file lives under a DIFFERENT "
                        "stage's own attempt raw dir (data/<run>/attempts/equilibration/attempt-N/"
                        "raw/), never under this summary attempt's own --output_dir, so the plain "
                        "same-dir lookup below can never find it without this.")
    p.add_argument("--mechanical_path", default=None,
                   help="Explicit path to the accepted mechanical attempt's mechanical.json -- "
                        "same cross-attempt-directory reasoning as --equilibration_path.")
    p.add_argument("--bulk_modulus_deform_path", default=None,
                   help="Explicit path to the accepted mechanical attempt's "
                        "bulk_modulus_deform.json (deformation-fallback runs only) -- same "
                        "cross-attempt-directory reasoning as --equilibration_path.")
    p.add_argument("--byproducts_spec", default=None,
                   help="Path to a JSON list of byproducts to surface, written by "
                        "run_campaign.do_summary from orchestration/scripts/track_registry.py. "
                        "Each entry: {name, produced_by, track, source_json, field, gate_field, "
                        "unit}. Passed as a file rather than imported because track_registry "
                        "lives in orchestration/ and these analysis scripts deploy separately "
                        "(same reason --equilibration_path is a path and not a lookup).")
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

    def _load_cross_attempt(name, explicit_path, flag_name):
        """Like _load, but for an artifact that lives under a DIFFERENT stage's own attempt raw
        dir (equilibration.json/mechanical.json/bulk_modulus_deform.json under the attempt-based
        run layout -- see --equilibration_path's help). explicit_path (already known from that
        stage's own returned outputs, threaded through by the caller) is checked first; only
        falls back to the plain same-dir lookup (which will not find a cross-attempt-directory
        file, matching the historical bug this replaces) when no explicit path was given."""
        if explicit_path:
            path = Path(explicit_path)
            if path.exists():
                return _load_json(path)
            artifacts_missing.append({"file": name, "found_in": None,
                                       "note": f"--{flag_name} given but not found: {explicit_path}"})
            return {}
        return _load(name)

    tg           = _load("thermal.json")
    # equilibration.json holds check_equilibration_comprehensive's own nested schema
    # (thermo.*/chain.*/spatial.*) at its top level, plus "density" (extract_equilibrated_
    # density's result) and "gate" (enforce_equilibration_gate's verdict) as sibling keys.
    eq_comp      = _load_cross_attempt("equilibration.json", args.equilibration_path, "equilibration_path")
    eq_dens      = eq_comp.get("density") or {}
    eq_gate      = eq_comp.get("gate") or {}
    bulk_deform  = _load_cross_attempt("bulk_modulus_deform.json", args.bulk_modulus_deform_path,
                                        "bulk_modulus_deform_path")
    bulk_murnaghan = _load_cross_attempt("mechanical.json", args.mechanical_path, "mechanical_path")

    # -----------------------------------------------------------------------
    # Results section
    # -----------------------------------------------------------------------
    # Tg resolution: single-rate MD Tg. A run may write thermal.json into a per-rate
    # subdir (tg_r<rate>/), so search recursively when the top-level file is absent (else
    # Tg silently drops from the summary).
    Tg_raw = tg.get("Tg_K")
    if Tg_raw is None and not tg:
        # Explicit canonical path wins over rglob to avoid alphabetical-order bugs
        # (tg_r160/ sorts before tg_r40/, picking the wrong faster-rate Tg as headline).
        if getattr(args, "tg_path", None) and Path(args.tg_path).exists():
            j = _load_json(Path(args.tg_path))
            if j.get("Tg_K") is not None:
                tg, Tg_raw = j, j.get("Tg_K")
        else:
            for cand in sorted(output_dir.rglob("thermal.json")):
                j = _load_json(cand)
                if j.get("Tg_K") is not None:
                    tg, Tg_raw = j, j.get("Tg_K")
                    break
        if tg:
            # Recovered from a per-rate subdir — the only artifact with its own discovery, so it
            # is not stranded and does not belong in artifacts_missing.
            artifacts_missing[:] = [m for m in artifacts_missing if m["file"] != "thermal.json"]

    # Measured values only -- no experimental comparison. Most runs are novel systems with no
    # curated experimental reference, so a PASS/FAIL grading column would be blank far more often
    # than not; compare against literature by hand (or via exp_lookup.json, written separately
    # for provenance) when a reference happens to exist for a given polymer.
    Tg_val = Tg_raw
    tg_basis = "raw_MD" if Tg_raw is not None else None
    tg_r2 = tg.get("r_squared")
    tg_quality = tg.get("fit_quality")

    rho_val = eq_dens.get("plateau_density_mean") or eq_dens.get("density_mean")

    # K-source precedence: murnaghan > deform.
    # Murnaghan is the primary glassy (300 K) and rubbery (T>Tg) method.
    # Deform (3-direction) is the fallback when Murnaghan EOS fails.
    # Born+NVT has been removed (PCFF+PPPM virial incompatibility, 2026-06-21).
    if bulk_murnaghan.get("B0_GPa") is not None:
        K_val    = bulk_murnaghan.get("B0_GPa")
        K_sem    = bulk_murnaghan.get("B0_sem_GPa")
        K_method = "murnaghan"
    elif bulk_deform.get("K_GPa") is not None:
        K_val    = bulk_deform.get("K_GPa")
        K_sem    = bulk_deform.get("K_sem_GPa")
        K_method = "deformation"
    else:
        K_val = K_sem = K_method = None

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
        "thermal":                 rel("thermal.json"),
        "tg_density_bins":         rel("tg_density_bins.csv"),
        "tg_fit_fig":              rel_fig("tg_fit.png"),
        "equilibration":           rel("equilibration.json"),
        "equilibration_fig":       rel_fig("equilibration_convergence.png"),
        "bulk_modulus_deform":     rel("bulk_modulus_deform.json"),
        "mechanical":              rel("mechanical.json"),
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
    # No producer in the engine-driven path currently emits mdanalysis_version (the tools that
    # once did -- end-to-end/RDF/Rg extraction -- are never invoked by run_campaign.py).
    mda_version = "unknown"

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
            # eq_gate (equilibration.json's "gate" section, the enforce_equilibration_gate
            # verdict) is the real record when present; --d05 is a caller-supplied fallback for
            # runs where that section hasn't been written (e.g. no gate ever ran).
            "D-05_convergence":  eq_gate.get("verdict") or args.d05,
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
                "grading_basis":  tg_basis,   # raw_MD, no rate-extrapolation applied
                "r_squared":      tg_r2,
                "fit_quality":    tg_quality,
                # True when the headline raw-MD fit still violates a hard physics constraint
                # (no valid alternative existed to swap in, per extract_thermal). Surfaced so the
                # headline Tg is not graded silently — treat the value as unreliable when set.
                "primary_fit_invalid": tg.get("primary_fit_invalid", False),
                "n_replicates":        args.n_replicates,
            },
            "density": {
                "value_g_cm3":    rho_val,
            },
            "bulk_modulus": {
                "value_GPa":      K_val,
                "sem_GPa":        K_sem,
                "method":         K_method,
            },
        },
        # Measurements this run produced without being asked for -- a Tg request already computes
        # thermal expansion, a transition width and a density at every swept temperature. All are
        # already in the extractor JSONs; only the surfacing is new.
        #
        # A SIBLING of results, deliberately not a key inside it: aggregate_replicates,
        # merge_arm_summaries and the polyjarvis_vs_radonpy scorer all read results by field path
        # and would break on an unexpected sub-dict. results keeps its exact three-key shape.
        #
        # Each entry carries its own gate verdict. A failing byproduct ANNOTATES -- it is never
        # in binding_gate_failure's vocabulary, so it cannot fail a run that did not ask for it.
        # Sparse: an entry appears only if its field actually resolved, so a reader can tell
        # "measured and doubtful" from "not measured".
        "byproducts": _collect_byproducts(args.byproducts_spec, {
            "thermal.json": tg, "equilibration.json": eq_comp,
        }),
        "convergence": {
            "verdict":            args.d05 or (("PASS" if eq_comp.get("overall_pass") else "FAIL")
                                              if eq_comp else None),
            "density_equilibrated": _dig(eq_comp, "thermo", "density_drift", "pass"),
            "energy_equilibrated":  _dig(eq_comp, "thermo", "energy_drift", "pass"),
            "density_drift_pct":    _dig(eq_comp, "thermo", "density_drift", "drift_pct"),
            # Accepted-but-suspect chain-relaxation conditions verdict alone hides -- see
            # _convergence_caveats. Empty list when none apply (including when eq_comp itself
            # never loaded), never null, so a consumer can always safely do `if caveats:`.
            "caveats":            _convergence_caveats(eq_comp),
        },
        "structural_checks": {
            "rg_cv":              _dig(eq_comp, "chain", "rg", "cv"),
            "rg_spread_flag":     _not(_dig(eq_comp, "chain", "rg", "pass")) if eq_comp else None,
            "kinetic_trap_flag":  _dig(eq_comp, "chain", "msd", "kinetic_trap_flag"),
            "diffusion_regime":   _dig(eq_comp, "chain", "msd", "diffusion_regime"),
            # msid_* previously had no home in run_summary.json at all -- see
            # GLOBAL_CHAIN_CONFIGURATION_NOT_RELAXED in convergence.caveats for the plain-English
            # flag; these are the raw numbers behind it.
            "msid_slope":                _dig(eq_comp, "chain", "msid", "slope"),
            "msid_large_s_slope":        _dig(eq_comp, "chain", "msid", "large_s", "slope"),
            "msid_large_s_gaussian_pass": _dig(eq_comp, "chain", "msid", "large_s", "gaussian_pass"),
            "ordered_flag":       _not(_dig(eq_comp, "spatial", "p2", "pass")) if eq_comp else None,
            "p2_mean":            _dig(eq_comp, "spatial", "p2", "p2_mean"),
            "heterogeneous_flag": (_not(_dig(eq_comp, "spatial", "density_homogeneity", "pass"))
                                   if eq_comp else None),
            "density_cv_mean":    _dig(eq_comp, "spatial", "density_homogeneity", "cv_mean"),
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
