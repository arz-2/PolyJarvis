#!/usr/bin/env python3
"""Generate the main-text 'Structural and equilibration diagnostics' table.

Reads each run's pre-computed equilibration_comprehensive.json (Rg + CV, MSID
Gaussian slope, end-to-end Ree, MSD alpha + kinetic-trap flag, C(t) relaxation,
nematic P2, density-homogeneity CV, energy drift) and reduces it to one row per
polymer (ensemble mean +/- s.d. over the 300 K replicates).

Outputs (self-contained under paper/csv/ so the paper does not reach into data/):
  csv/structure_diagnostics.csv          -- per-system summary (the main-text table)
  csv/structure_diagnostics_perrun.csv   -- every kept run (feeds the SI full table)
  csv/structure_diagnostics_manifest.json-- which reps kept/dropped and why + floors
and prints ready-to-paste LaTeX rows to stdout.

Data-cleanliness rules (see plan):
  - exclude the stray PROPSULFIDE_AGENT directory (not one of the 9 systems)
  - drop C_inf (populated for only 11/37 runs, values nonphysical) -> use MSID slope
  - restrict to 300 K replicates (T_mean in [280, 320]); 4 reps were run at elevated
    T (PEEK1 770, PMMA1 550, PSU1 700, PVC1 530) and are excluded from this table
  - density homogeneity is judged as measured voxel CV vs the random-packing Poisson
    floor at that resolution (NOT the absolute 0.25 heterogeneous_flag, which trips on
    PMMA/PSU purely from the threshold); all systems sit within ~0.07 of the floor
  - PVC4 energy drift = 9.56% is an artifact (others <1%) -> excluded from the energy
    mean (recorded in the manifest); robust median also reported
"""

import json
import glob
import os
import re
import math

DATA_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "csv")
os.makedirs(OUT_DIR, exist_ok=True)

# Display order, matching the other paper/gen_figure*.py scripts.
POLYMERS = ["cis-PBD", "PE", "PEG", "PLA", "PMMA", "PS", "PSU", "PVC", "PEEK"]
T_LO, T_HI = 280.0, 320.0          # 300 K production window
EDRIFT_ARTIFACT = 5.0              # energy-drift % above this is a measurement artifact


def run_to_polymer(run):
    """'cis-PBD1' -> 'cis-PBD', 'PMMA2' -> 'PMMA'."""
    return re.sub(r"\d+$", "", run)


def mean_sd(vals):
    vals = [v for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v))]
    if not vals:
        return (float("nan"), float("nan"), 0)
    m = sum(vals) / len(vals)
    if len(vals) < 2:
        return (m, 0.0, len(vals))
    var = sum((v - m) ** 2 for v in vals) / (len(vals) - 1)
    return (m, math.sqrt(var), len(vals))


def median(vals):
    vals = sorted(v for v in vals if v is not None and not (isinstance(v, float) and math.isnan(v)))
    if not vals:
        return float("nan")
    n = len(vals)
    return vals[n // 2] if n % 2 else 0.5 * (vals[n // 2 - 1] + vals[n // 2])


# ---- gather every run -------------------------------------------------------
perrun = []          # kept 300 K runs
dropped = []         # {run, reason, T}
for path in sorted(glob.glob(os.path.join(DATA_DIR, "*/raw/equilibration_comprehensive.json"))):
    run = path.split("/")[-3]
    if run == "PROPSULFIDE_AGENT":
        dropped.append({"run": run, "reason": "stray dir, not a benchmark system", "T": None})
        continue
    if run_to_polymer(run) not in POLYMERS:
        dropped.append({"run": run, "reason": "unknown polymer", "T": None})
        continue
    d = json.load(open(path))
    T = (d.get("thermo", {}).get("meta", {}) or {}).get("T_mean")
    ch, sp, th = d.get("chain", {}), d.get("spatial", {}), d.get("thermo", {})
    rg = ch.get("rg", {}); msid = ch.get("msid", {}); ree = ch.get("ree", {})
    msd = ch.get("msd", {}); ct = ch.get("ct", {})
    p2 = sp.get("p2", {}); dh = sp.get("density_homogeneity", {})
    rec = {
        "run": run, "polymer": run_to_polymer(run), "T_mean": T,
        "Rg_A": rg.get("mean_Rg_A"),
        "Rg_CV_pct": (rg.get("cv") * 100) if rg.get("cv") is not None else None,
        "MSID_slope": msid.get("slope"),
        "MSID_gaussian_pass": msid.get("gaussian_pass"),
        "P2": p2.get("p2_mean"),
        "dens_CV_pct": (dh.get("cv_mean") * 100) if dh.get("cv_mean") is not None else None,
        "poisson_CV_pct": (dh.get("poisson_cv") * 100) if dh.get("poisson_cv") is not None else None,
        "heterogeneous_flag": dh.get("heterogeneous_flag"),
        "E_drift_pct": (th.get("energy_drift", {}) or {}).get("drift_pct"),
        # dynamics (SI only, not in the main table headline)
        "Ree_A": ree.get("mean_R_ee_A"), "Ree_sd_A": ree.get("std_R_ee_A"),
        "MSD_alpha": msd.get("alpha"), "MSD_regime": msd.get("diffusion_regime"),
        "kinetic_trap_flag": msd.get("kinetic_trap_flag"),
        "ct_tau_relax_ps": ct.get("tau_relax_ps"), "ct_beta": ct.get("beta"),
    }
    if T is None or not (T_LO <= T <= T_HI):
        dropped.append({"run": run, "reason": f"elevated-T production dump (T={T} K)", "T": T})
        continue
    perrun.append(rec)

# ---- per-system reduction ---------------------------------------------------
summary = []
for p in POLYMERS:
    runs = [r for r in perrun if r["polymer"] == p]
    rg_m, rg_s, n = mean_sd([r["Rg_A"] for r in runs])
    cv_m, cv_s, _ = mean_sd([r["Rg_CV_pct"] for r in runs])
    ms_m, ms_s, _ = mean_sd([r["MSID_slope"] for r in runs])
    p2_m, p2_s, _ = mean_sd([r["P2"] for r in runs])
    dh_m, dh_s, _ = mean_sd([r["dens_CV_pct"] for r in runs])
    floor_m, _, _ = mean_sd([r["poisson_CV_pct"] for r in runs])
    # energy drift: drop measurement artifacts (>5%) from the mean; keep robust median
    e_all = [r["E_drift_pct"] for r in runs]
    e_clean = [e for e in e_all if e is not None and e <= EDRIFT_ARTIFACT]
    e_excluded = [r["run"] for r in runs if r["E_drift_pct"] is not None and r["E_drift_pct"] > EDRIFT_ARTIFACT]
    e_m, e_s, _ = mean_sd(e_clean)
    summary.append({
        "polymer": p, "n_reps": n,
        "Rg_A": rg_m, "Rg_A_sd": rg_s,
        "Rg_CV_pct": cv_m, "Rg_CV_pct_sd": cv_s,
        "MSID_slope": ms_m, "MSID_slope_sd": ms_s,
        "P2": p2_m, "P2_sd": p2_s,
        "dens_CV_pct": dh_m, "dens_CV_pct_sd": dh_s,
        "poisson_CV_pct": floor_m,
        "dens_excess_pct": dh_m - floor_m,
        "E_drift_pct": e_m, "E_drift_pct_sd": e_s,
        "E_drift_median_pct": median(e_all),
        "E_drift_excluded": e_excluded,
        "het_flag_any": any(r["heterogeneous_flag"] for r in runs),
    })

# ---- write CSVs -------------------------------------------------------------
def write_csv(fname, rows, cols):
    with open(os.path.join(OUT_DIR, fname), "w") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(
                ("" if r.get(c) is None else
                 (f"{r[c]:.4f}" if isinstance(r.get(c), float) else str(r.get(c))))
                for c in cols) + "\n")

write_csv("structure_diagnostics.csv", summary,
          ["polymer", "n_reps", "Rg_A", "Rg_A_sd", "Rg_CV_pct", "Rg_CV_pct_sd",
           "MSID_slope", "MSID_slope_sd", "P2", "P2_sd",
           "dens_CV_pct", "dens_CV_pct_sd", "poisson_CV_pct", "dens_excess_pct",
           "E_drift_pct", "E_drift_pct_sd", "E_drift_median_pct", "het_flag_any"])

write_csv("structure_diagnostics_perrun.csv", perrun,
          ["run", "polymer", "T_mean", "Rg_A", "Rg_CV_pct", "MSID_slope",
           "MSID_gaussian_pass", "P2", "dens_CV_pct", "poisson_CV_pct",
           "heterogeneous_flag", "E_drift_pct", "Ree_A", "Ree_sd_A",
           "MSD_alpha", "MSD_regime", "kinetic_trap_flag", "ct_tau_relax_ps", "ct_beta"])

manifest = {
    "source": "data/<RUN>/raw/equilibration_comprehensive.json",
    "T_window_K": [T_LO, T_HI],
    "n_runs_kept": len(perrun),
    "kept_runs": [r["run"] for r in perrun],
    "dropped": dropped,
    "energy_drift_artifact_threshold_pct": EDRIFT_ARTIFACT,
    "notes": {
        "C_inf": "dropped (populated 11/37, nonphysical); MSID slope used instead",
        "density_homogeneity": "judged as measured voxel CV vs random-packing Poisson "
                               "floor; heterogeneous_flag (abs 0.25) trips on PMMA/PSU "
                               "but excess over floor is small (~0.04-0.07)",
    },
}
json.dump(manifest, open(os.path.join(OUT_DIR, "structure_diagnostics_manifest.json"), "w"), indent=2)

# ---- LaTeX rows + console summary ------------------------------------------
print("=== dropped runs ===")
for d in dropped:
    print(f"  {d['run']:18} {d['reason']}")
print(f"\nkept {len(perrun)} runs across {len(POLYMERS)} systems\n")

print("=== LaTeX rows (Polymer | <Rg>+-sd | RgCV% | MSID+-sd | P2+-sd | densCV% (floor) | Edrift%+-sd) ===")
for s in summary:
    print(
        f"{s['polymer']:8} & {s['Rg_A']:.1f} $\\pm$ {s['Rg_A_sd']:.1f} "
        f"& {s['Rg_CV_pct']:.0f} "
        f"& {s['MSID_slope']:.2f} $\\pm$ {s['MSID_slope_sd']:.2f} "
        f"& {s['P2']:.3f} $\\pm$ {s['P2_sd']:.3f} "
        f"& {s['dens_CV_pct']:.0f} ({s['poisson_CV_pct']:.0f}) "
        f"& {s['E_drift_pct']:.2f} $\\pm$ {s['E_drift_pct_sd']:.2f} \\\\"
    )

print("\n=== plain summary ===")
print(f"{'sys':8} {'n':>2} {'Rg':>5} {'RgCV':>5} {'MSID':>5} {'P2':>6} {'dCV':>5} {'floor':>5} {'exc':>5} {'Edrft':>6} {'het?':>5}")
for s in summary:
    print(f"{s['polymer']:8} {s['n_reps']:>2} {s['Rg_A']:>5.1f} {s['Rg_CV_pct']:>5.1f} "
          f"{s['MSID_slope']:>5.2f} {s['P2']:>6.3f} {s['dens_CV_pct']:>5.1f} "
          f"{s['poisson_CV_pct']:>5.1f} {s['dens_excess_pct']:>5.1f} "
          f"{s['E_drift_pct']:>6.2f} {str(s['het_flag_any']):>5}")
    if s["E_drift_excluded"]:
        print(f"         (energy-drift artifacts excluded from mean: {s['E_drift_excluded']})")
