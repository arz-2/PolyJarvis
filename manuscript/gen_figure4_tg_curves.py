#!/usr/bin/env python3
"""Generate the Tg figure: density vs temperature, replicate-ENSEMBLE-MEAN curve
per polymer, for the 9-polymer EMC/PCFF benchmark.

This replaces the old single-replicate / F-stat version (replot_from_tool.py).
For each polymer:
  * each of its 4 replicates contributes the density-vs-T sweep at the cooling
    rate that produced its reported per-replicate Tg (property_comparison.md);
  * the 4 sweeps are pooled and averaged per temperature (mean +/- s.d.);
  * a bilinear fit is drawn with its breakpoint FIXED at the property_comparison
    system-mean Tg, so the gold star (= reported mean Tg) sits exactly on the kink;
  * the green band is the experimental Tg window.

Selected per-replicate bins are copied into manuscript/csv/<RUN>_bins.csv so manuscript/ is
self-contained and reproducible.
"""
import os, glob, json, shutil
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "data"))
CSV_OUT = os.path.join(HERE, "csv")
FIG_OUT = os.path.join(HERE, "figures")
os.makedirs(CSV_OUT, exist_ok=True)
os.makedirs(FIG_OUT, exist_ok=True)

# ── benchmark constants (from manuscript/property_comparison.md) ────────────────────
# display order shared with the density / modulus figures
POLYMERS = ["cis-PBD", "PE", "PEG", "PLA", "PMMA", "PS", "PSU", "PVC", "PEEK"]

# reported per-replicate Tg (Tg_sim column) — used to pick each replicate's rate
REPORTED_TG = {
    "cis-PBD": {1: 172.5, 2: 191.6, 3: 180.8, 4: 179.6},
    "PE":      {1: 230.7, 2: 231.5, 3: 209.4, 4: 213.0},
    "PEG":     {1: 218.8, 2: 238.7, 3: 244.4, 4: 236.7},
    "PLA":     {1: 425.2, 2: 428.6, 3: 430.0, 4: 446.9},
    "PMMA":    {1: 340.0, 2: 403.4, 3: 379.0, 4: 408.6},
    "PS":      {1: 375.9, 2: 436.9, 3: 376.5, 4: 434.0},
    "PSU":     {1: 499.7, 2: 498.4, 3: 502.0, 4: 496.4},
    "PVC":     {1: 347.9, 2: 307.9, 3: 310.6, 4: 315.1},
    "PEEK":    {1: 532.7, 2: 523.6, 3: 551.7, 4: 512.8},
}
# system-mean Tg +/- s.d. (per-system summary table) — the headline number/star
MEAN_TG = {
    "cis-PBD": (181.1, 7.9), "PE": (221.2, 11.6), "PEG": (234.7, 11.1),
    "PLA": (432.7, 9.7), "PMMA": (382.8, 31.3), "PS": (405.8, 34.2),
    "PSU": (499.1, 2.3), "PVC": (320.4, 18.6), "PEEK": (530.2, 16.5),
}
EXP_TG = {  # experimental Tg (single midpoint/representative value; K)
    # taken verbatim from the main-text benchmark table (tab:benchmarks) so the
    # figure references the same experimental Tg as the reported deviations
    "cis-PBD": 174, "PE": 195, "PEG": 206,
    "PLA": 331, "PMMA": 378, "PS": 373,
    "PSU": 463, "PVC": 354, "PEEK": 418,
}
COLORS = {
    "cis-PBD": "#4285F4", "PE": "#34A853", "PEG": "#A142F4", "PLA": "#00ACC1",
    "PMMA": "#EA4335", "PS": "#FB8C00", "PSU": "#6D4C41", "PVC": "#C0CA33",
    "PEEK": "#5E35B1",
}
# directory stem per polymer (the manuscript/data/<stem>N run folders)
STEM = {p: p for p in POLYMERS}  # folder names match labels exactly


def _candidate_dirs(run_dir):
    """Return [(dir, tg_summary.json)] for a run: rate subdirs + top-level,
    excluding contaminated dirs and dirs without a bins CSV."""
    out = []
    top_ts = os.path.join(run_dir, "tg_summary.json")
    top_bins = os.path.join(run_dir, "tg_density_bins.csv")
    if os.path.isfile(top_ts) and os.path.isfile(top_bins):
        out.append((run_dir, top_ts))
    for sub in sorted(glob.glob(os.path.join(run_dir, "tg_*"))):
        if "contaminat" in os.path.basename(sub):
            continue
        ts = os.path.join(sub, "tg_summary.json")
        bins = os.path.join(sub, "tg_density_bins.csv")
        if os.path.isfile(ts) and os.path.isfile(bins):
            out.append((sub, ts))
    return out


def select_bins(polymer, rep):
    """Pick the bins CSV whose fit Tg_K is closest to the reported per-replicate
    Tg; fall back to the slowest (lowest K/ns) rate dir."""
    run_dir = os.path.join(DATA, f"{STEM[polymer]}{rep}", "raw")
    reported = REPORTED_TG[polymer][rep]
    cands = _candidate_dirs(run_dir)
    if not cands:
        return None
    scored = []
    for d, ts in cands:
        try:
            tg = json.load(open(ts)).get("Tg_K")
        except Exception:
            continue
        if tg is None:
            continue
        # rate number for tie-break / fallback (smaller = slower)
        base = os.path.basename(d)
        rate = 0.0
        if base.startswith("tg_r"):
            num = "".join(ch for ch in base[4:] if (ch.isdigit() or ch == "."))
            rate = float(num) if num else 1e9
        scored.append((abs(tg - reported), rate, d, tg))
    if not scored:
        return None
    scored.sort(key=lambda s: (s[0], s[1]))
    diff, rate, d, tg = scored[0]
    bins = os.path.join(d, "tg_density_bins.csv")
    return {"dir": d, "bins": bins, "tg_fit": tg, "diff": diff}


def anchored_bilinear(T, rho, tg):
    """Continuous piecewise-linear fit with the knot fixed at tg.
    Basis: rho = c + a_g*min(T-tg,0) + a_r*max(T-tg,0). Returns (c, a_g, a_r, r2)."""
    dT = T - tg
    X = np.column_stack([np.ones_like(dT), np.minimum(dT, 0.0), np.maximum(dT, 0.0)])
    coef, *_ = np.linalg.lstsq(X, rho, rcond=None)
    pred = X @ coef
    ss_res = np.sum((rho - pred) ** 2)
    ss_tot = np.sum((rho - rho.mean()) ** 2)
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    c, a_g, a_r = coef
    return c, a_g, a_r, r2


# ── gather + pool ─────────────────────────────────────────────────────────────
pooled = {}
manifest = {}
for p in POLYMERS:
    frames = []
    manifest[p] = []
    for rep in (1, 2, 3, 4):
        sel = select_bins(p, rep)
        if sel is None:
            print(f"  WARN: no bins for {p}{rep}")
            continue
        df = pd.read_csv(sel["bins"])
        # copy into manuscript/csv for reproducibility
        shutil.copyfile(sel["bins"], os.path.join(CSV_OUT, f"{p}{rep}_bins.csv"))
        frames.append((rep, df["temperature"].values, df["mean_density"].values))
        manifest[p].append({"rep": rep, "tg_fit": round(sel["tg_fit"], 1),
                            "reported": REPORTED_TG[p][rep],
                            "dir": os.path.relpath(sel["dir"], DATA)})
    # pool on the common temperature grid (5 K bins)
    allT = np.concatenate([T for _, T, _ in frames])
    grid = np.arange(np.floor(allT.min() / 5) * 5, np.ceil(allT.max() / 5) * 5 + 1, 5)
    stacks = []
    for _, T, R in frames:
        s = np.full_like(grid, np.nan, dtype=float)
        # nearest-bin assignment
        for t, r in zip(T, R):
            idx = int(round((t - grid[0]) / 5))
            if 0 <= idx < len(grid):
                s[idx] = r
        stacks.append(s)
    M = np.vstack(stacks)
    n = np.sum(~np.isnan(M), axis=0)
    keep = n >= 1
    mean = np.full(len(n), np.nan)
    sd = np.zeros(len(n))
    with np.errstate(invalid="ignore"):
        mean[keep] = np.nanmean(M[:, keep], axis=0)
        multi = keep & (n >= 2)
        sd[multi] = np.nanstd(M[:, multi], axis=0, ddof=1)
    pooled[p] = {"T": grid[keep], "rho": mean[keep], "sd": np.nan_to_num(sd[keep]),
                 "n": n[keep], "reps": [(T, R) for _, T, R in frames]}

# ── plot 3x3 master ───────────────────────────────────────────────────────────
fig, axes = plt.subplots(3, 3, figsize=(13, 11))
for ax, p in zip(axes.flat, POLYMERS):
    d = pooled[p]
    T, rho, sd = d["T"], d["rho"], d["sd"]
    color = COLORS[p]
    tg, tg_sd = MEAN_TG[p]

    # mean +/- s.d. data points
    ax.errorbar(T, rho, yerr=sd, fmt="o", color=color, markersize=4,
                capsize=2, elinewidth=0.7, markeredgecolor="k",
                markeredgewidth=0.3, zorder=5, label="MD mean ± s.d. (4 reps)")

    # anchored bilinear fit (knot fixed at the reported mean Tg)
    c, a_g, a_r, r2 = anchored_bilinear(T, rho, tg)
    T_lo = np.linspace(T.min(), tg, 100)
    T_hi = np.linspace(tg, T.max(), 100)
    ax.plot(T_lo, c + a_g * (T_lo - tg), "k-", lw=2, zorder=6, label="Glassy fit")
    ax.plot(T_hi, c + a_r * (T_hi - tg), "k--", lw=2, zorder=6, label="Rubbery fit")

    # gold star at (mean Tg, fit value) — sits on the kink by construction
    ax.plot(tg, c, "*", color="gold", markersize=20, markeredgecolor="k",
            markeredgewidth=1.2, zorder=10)
    ax.errorbar(tg, c, xerr=tg_sd, ecolor="goldenrod", elinewidth=1.5,
                capsize=3, zorder=9)

    # experimental Tg reference (single benchmark-table value)
    exp = EXP_TG[p]
    ax.axvline(exp, color="green", ls="--", lw=1.8, alpha=0.75, zorder=1)

    ax.set_title(f"{p}", fontsize=13, fontweight="bold")
    txt = (f"$T_g$ = {tg:.0f} ± {tg_sd:.0f} K\n"
           f"Exp = {exp:.0f} K\n"
           f"fit $R^2$ = {r2:.3f}")
    ax.text(0.04, 0.04, txt, transform=ax.transAxes, fontsize=8.5,
            va="bottom", ha="left",
            bbox=dict(boxstyle="round,pad=0.35", facecolor="wheat", alpha=0.8))
    ax.set_xlabel("Temperature (K)", fontsize=10)
    ax.set_ylabel("Density (g/cm³)", fontsize=10)
    ax.grid(True, alpha=0.3)

# one shared legend (proxy handles from the first axis)
h, l = axes.flat[0].get_legend_handles_labels()
star = plt.Line2D([], [], marker="*", color="gold", markeredgecolor="k",
                  markersize=16, ls="none", label="Mean $T_g$ (± s.d.)")
band = plt.Line2D([], [], color="green", ls="--", lw=1.8, label="Exp. $T_g$ (benchmark table)")
fig.legend(handles=h + [star, band], loc="upper center", ncol=5,
           fontsize=10, frameon=True, bbox_to_anchor=(0.5, 1.005))

fig.suptitle("Density vs. temperature — replicate-ensemble mean",
             fontsize=14, fontweight="bold", y=1.03)
fig.tight_layout()
for ext in ("pdf", "png"):
    fig.savefig(os.path.join(FIG_OUT, f"figure4_Tg_curves.{ext}"),
                dpi=200, bbox_inches="tight")
print("Saved figures/figure4_Tg_curves.{pdf,png}")

# write the selection manifest for auditing
with open(os.path.join(CSV_OUT, "tg_selection_manifest.json"), "w") as fh:
    json.dump(manifest, fh, indent=2)
print("Saved csv/tg_selection_manifest.json")
for p in POLYMERS:
    diffs = [f"{m['rep']}:{m['tg_fit']}~{m['reported']}" for m in manifest[p]]
    print(f"  {p:8} {'  '.join(diffs)}")
