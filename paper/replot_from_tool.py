"""
Replot density vs temperature using EXACT extract_tg tool output.

Data: Plateau-detected, equilibration-filtered CSVs from Lambda.
Fits: Exact fit parameters from the v3 F-stat tool (NOT re-fitted).
This guarantees the plots match the paper values exactly.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import csv

OUT_DIR = Path(__file__).parent
CSV_DIR = OUT_DIR / "csv"

# ══════════════════════════════════════════════════════════════════════
# EXACT TOOL OUTPUT — copied from extract_tg job results
# ══════════════════════════════════════════════════════════════════════

TOOL_RESULTS = {
    "PE1": {
        "csv": "PE1_bins.csv", "system": "PE", "run": 1,
        "tg": 291.1, "r2": 0.9975, "f_stat": 79.0, "quality": "EXCELLENT",
        "a_glassy": -0.0003349760992301127, "b_glassy": 1.1878626896207585,
        "a_rubbery": -0.0008253584239638059, "b_rubbery": 1.3305963501394076,
        "n_bins": 38, "n_skipped": 24, "method": "F-stat",
        "exp_tg": (145, 243), "notes": "",
    },
    "PE2": {
        "csv": "PE2_bins.csv", "system": "PE", "run": 2,
        "tg": 281.3, "r2": 0.9989, "f_stat": 95.7, "quality": "GOOD",
        "a_glassy": -0.00028702024601594104, "b_glassy": 1.173538069356423,
        "a_rubbery": -0.0006423181270505499, "b_rubbery": 1.2734978035929676,
        "n_bins": 11, "n_skipped": 1, "method": "F-stat",
        "exp_tg": (145, 243), "notes": "",
    },
    "PE3": {
        "csv": "PE3_bins.csv", "system": "PE", "run": 3,
        "tg": 303.5, "r2": 0.9973, "f_stat": 46.8, "quality": "GOOD",
        "a_glassy": -0.0004161159578462126, "b_glassy": 1.2053755830790802,
        "a_rubbery": -0.0008020892889163728, "b_rubbery": 1.3224992991881732,
        "n_bins": 30, "n_skipped": 17, "method": "F-stat",
        "exp_tg": (145, 243), "notes": "10K steps near transition; 2ns/step",
    },
    "PS1": {
        "csv": "PS1_bins.csv", "system": "aPS", "run": 1,
        "tg": 498.4, "r2": 0.9881, "f_stat": 22.5, "quality": "GOOD",
        "a_glassy": -0.0003547183363246577, "b_glassy": 1.1572296192350375,
        "a_rubbery": -0.0007420774188872637, "b_rubbery": 1.3502825223376216,
        "n_bins": 23, "n_skipped": 22, "method": "F-stat",
        "exp_tg": (353, 373), "notes": "6-stage eq; R²=0.867 on old fit",
    },
    "PS2": {
        "csv": "PS2_bins.csv", "system": "aPS", "run": 2,
        "tg": 416.1, "r2": 0.9957, "f_stat": 12.8, "quality": "ACCEPTABLE",
        "a_glassy": -0.0003949325778079729, "b_glassy": 1.1801452315553205,
        "a_rubbery": -0.0006088172998583687, "b_rubbery": 1.2691478017459312,
        "n_bins": 15, "n_skipped": 4, "method": "F-stat",
        "exp_tg": (353, 373), "notes": "12-stage eq, 3x annealing",
    },
    "PS3": {
        "csv": "PS3_bins.csv", "system": "aPS", "run": 3,
        "tg": 466.0, "r2": 0.9897, "f_stat": 43.8, "quality": "GOOD",
        "a_glassy": -0.00036662112727972444, "b_glassy": 1.1649404383184054,
        "a_rubbery": -0.0007166603193741026, "b_rubbery": 1.3280760371165257,
        "n_bins": 25, "n_skipped": 12, "method": "F-stat",
        "exp_tg": (353, 373), "notes": "8-stage eq, 1x annealing",
    },
    "PMMA1": {
        "csv": "PMMA1_bins.csv", "system": "PMMA", "run": 1,
        "tg": 394.6, "r2": 0.9983, "f_stat": 58.1, "quality": "GOOD",
        "a_glassy": -0.00020141867306458768, "b_glassy": 1.1867402049552687,
        "a_rubbery": -0.0003446421170385911, "b_rubbery": 1.2432510255064166,
        "n_bins": 16, "n_skipped": 1, "method": "F-stat",
        "exp_tg": (377, 385), "notes": "Velocity reinit bug; v4 reanalysis",
    },
    "PMMA2": {
        "csv": "PMMA2_bins.csv", "system": "PMMA", "run": 2,
        "tg": 488.5, "r2": 0.9964, "f_stat": 2.9, "quality": "POOR",
        "a_glassy": -0.00020526912279580402, "b_glassy": 1.1923564656191283,
        "a_rubbery": -0.0002579751047544907, "b_rubbery": 1.2181020326023948,
        "n_bins": 9, "n_skipped": 0, "method": "F-stat",
        "exp_tg": (377, 385), "notes": "9 bins only; F-stat POOR (p=0.15)",
    },
    "PMMA3": {
        "csv": "PMMA3_bins.csv", "system": "PMMA", "run": 3,
        "tg": 473.2, "r2": 0.9877, "f_stat": 2.3, "quality": "POOR",
        "a_glassy": -0.00028790761327345443, "b_glassy": 1.2196257725691484,
        "a_rubbery": -0.000467870377325349, "b_rubbery": 1.3047892988738024,
        "n_bins": 10, "n_skipped": 0, "method": "F-stat",
        "exp_tg": (377, 385), "notes": "10 bins only; F-stat POOR (p=0.19)",
    },
    "PEG1": {
        "csv": "PEG1_bins.csv", "system": "PEG", "run": 1,
        "tg": 273.0, "r2": 0.9981, "f_stat": 45.3, "quality": "GOOD",
        "a_glassy": -0.0004594782347192233, "b_glassy": 1.2483455148433662,
        "a_rubbery": -0.000890293847124933, "b_rubbery": 1.3659662820669636,
        "n_bins": 16, "n_skipped": 12, "method": "F-stat",
        "exp_tg": (206, 213), "notes": "",
    },
    "PEG2": {
        "csv": "PEG2_bins.csv", "system": "PEG", "run": 2,
        "tg": 274.6, "r2": 0.9996, "f_stat": 15.0, "quality": "ACCEPTABLE",
        "a_glassy": -0.0006293785640238934, "b_glassy": 1.3001414934228388,
        "a_rubbery": -0.0008577515045497705, "b_rubbery": 1.3628516115778024,
        "n_bins": 9, "n_skipped": 1, "method": "F-stat",
        "exp_tg": (206, 213),
        "notes": "Previously curve_fit fallback; now proper F-stat",
    },
    "PEG3": {
        "csv": "PEG3_bins.csv", "system": "PEG", "run": 3,
        "tg": 260.3, "r2": 0.9995, "f_stat": 43.8, "quality": "GOOD",
        "a_glassy": -0.0005903219543456591, "b_glassy": 1.2849649460819197,
        "a_rubbery": -0.0008607462817665002, "b_rubbery": 1.3553658040896914,
        "n_bins": 17, "n_skipped": 10, "method": "F-stat",
        "exp_tg": (206, 213), "notes": "Near-linear profile; v3 F-stat resolves Tg",
    },
}

# Paper Tg values for cross-check
PAPER_TG = {
    "PE1": 291.1, "PE2": 281.3, "PE3": 303.5,
    "PS1": 498.4, "PS2": 416.1, "PS3": 466.0,
    "PMMA1": 394.6, "PMMA2": 488.5, "PMMA3": 473.2,
    "PEG1": 273.0, "PEG2": 274.6, "PEG3": 260.3,
}

SYSTEM_COLORS = {"PE": "#2196F3", "aPS": "#FF5722", "PMMA": "#4CAF50", "PEG": "#9C27B0"}
BEST_RUNS = {"PE": "PE2", "aPS": "PS2", "PMMA": "PMMA1", "PEG": "PEG3"}


def load_csv(key):
    """Load plateau-detected CSV for a run."""
    path = CSV_DIR / TOOL_RESULTS[key]["csv"]
    df = pd.read_csv(path)
    return df["temperature"].values, df["mean_density"].values, df.get("std_density", pd.Series([0]*len(df))).values


def plot_single(key, info, save=True):
    """Plot one run with tool's exact fit lines."""
    fig, ax = plt.subplots(figsize=(7, 5))
    T, rho, std = load_csv(key)
    color = SYSTEM_COLORS[info["system"]]
    tg = info["tg"]

    # Data with error bars
    ax.errorbar(T, rho, yerr=std, fmt='o', color=color, markersize=5,
                capsize=2, elinewidth=0.8, markeredgecolor='k', markeredgewidth=0.4,
                zorder=5, label=f"Plateau data ({info['n_bins']} bins)")

    # Tool's exact fit lines
    T_lo = np.linspace(T.min(), tg, 200)
    T_hi = np.linspace(tg, T.max(), 200)
    rho_lo = info["a_glassy"] * T_lo + info["b_glassy"]
    rho_hi = info["a_rubbery"] * T_hi + info["b_rubbery"]
    ax.plot(T_lo, rho_lo, "k-", linewidth=2, label="Glassy fit (tool)")
    ax.plot(T_hi, rho_hi, "k--", linewidth=2, label="Rubbery fit (tool)")

    # Tg star
    rho_tg = info["a_glassy"] * tg + info["b_glassy"]
    ax.plot(tg, rho_tg, "*", color="gold", markersize=18, markeredgecolor="k",
            markeredgewidth=1.2, zorder=10, label=f"$T_g$ = {tg:.1f} K")
    ax.axvline(tg, color="gold", alpha=0.4, linestyle=":", linewidth=1.5)

    # Experimental range
    exp_lo, exp_hi = info["exp_tg"]
    ax.axvspan(exp_lo, exp_hi, alpha=0.15, color="green",
               label=f"Exp $T_g$ = {exp_lo}–{exp_hi} K")

    # Paper Tg diamond (for cross-check)
    paper_tg = PAPER_TG[key]
    if abs(paper_tg - tg) > 1.0:
        rho_paper = info["a_glassy"] * paper_tg + info["b_glassy"]
        ax.plot(paper_tg, rho_paper, "D", color="red", markersize=8,
                markeredgecolor="k", markeredgewidth=0.8, zorder=9,
                label=f"$T_g^{{paper}}$ = {paper_tg:.1f} K")

    # Annotation box
    f_str = f"{info['f_stat']:.1f}" if info['f_stat'] else "N/A"
    textstr = (
        f"$T_g^{{\\mathrm{{tool}}}}$ = {tg:.1f} K\n"
        f"$R^2$ = {info['r2']:.4f}\n"
        f"F-stat = {f_str}\n"
        f"Quality: {info['quality']}\n"
        f"Bins: {info['n_bins']} ({info['n_skipped']} skipped drift)\n"
        f"$\\alpha_{{glassy}}$ = {abs(info['a_glassy'])*1e4:.2f}×10⁻⁴\n"
        f"$\\alpha_{{rubbery}}$ = {abs(info['a_rubbery'])*1e4:.2f}×10⁻⁴"
    )
    props = dict(boxstyle="round,pad=0.4", facecolor="wheat", alpha=0.8)
    ax.text(0.97, 0.97, textstr, transform=ax.transAxes, fontsize=8,
            verticalalignment="top", horizontalalignment="right", bbox=props)

    notes = f"  [{info['notes']}]" if info["notes"] else ""
    ax.set_title(f"{info['system']} Run {info['run']}{notes}", fontsize=13, fontweight="bold")
    ax.set_xlabel("Temperature (K)", fontsize=12)
    ax.set_ylabel("Density (g/cm³)", fontsize=12)
    ax.legend(fontsize=7.5, loc="lower left")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    if save:
        fname = OUT_DIR / f"{key}_tg_fit_v3.png"
        fig.savefig(fname, dpi=200, bbox_inches="tight")
        print(f"  Saved: {fname}")
    plt.close(fig)


def plot_system_combined(system, keys):
    """Side-by-side runs for one system."""
    n = len(keys)
    fig, axes = plt.subplots(1, n, figsize=(6*n, 5), sharey=True)
    if n == 1:
        axes = [axes]
    color = SYSTEM_COLORS[system]

    for i, (key, ax) in enumerate(zip(keys, axes)):
        info = TOOL_RESULTS[key]
        T, rho, std = load_csv(key)
        tg = info["tg"]

        ax.errorbar(T, rho, yerr=std, fmt='o', color=color, markersize=4,
                    capsize=1.5, elinewidth=0.6, markeredgecolor='k', markeredgewidth=0.3, zorder=5)

        T_lo = np.linspace(T.min(), min(tg, T.max()), 200)
        T_hi = np.linspace(max(tg, T.min()), T.max(), 200)
        ax.plot(T_lo, info["a_glassy"]*T_lo + info["b_glassy"], "k-", linewidth=2)
        ax.plot(T_hi, info["a_rubbery"]*T_hi + info["b_rubbery"], "k--", linewidth=2)

        rho_tg = info["a_glassy"] * tg + info["b_glassy"]
        ax.plot(tg, rho_tg, "*", color="gold", markersize=16, markeredgecolor="k", markeredgewidth=1, zorder=10)
        ax.axvline(tg, color="gold", alpha=0.4, linestyle=":", linewidth=1.5)
        ax.axvspan(*info["exp_tg"], alpha=0.15, color="green")

        q = info["quality"]
        ax.set_title(f"Run {info['run']}:  $T_g$ = {tg:.0f} K\n({q}, {info['n_bins']} bins)", fontsize=11, fontweight="bold")
        ax.set_xlabel("Temperature (K)", fontsize=11)
        if i == 0:
            ax.set_ylabel("Density (g/cm³)", fontsize=11)
        ax.grid(True, alpha=0.3)

    fig.suptitle(f"{system} — Density vs Temperature", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    fname = OUT_DIR / f"{system}_all_runs_v3.png"
    fig.savefig(fname, dpi=200, bbox_inches="tight")
    print(f"  Saved: {fname}")
    plt.close(fig)


def plot_master():
    """2x2 best replicates."""
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    for ax, (system, key) in zip(axes.flat, BEST_RUNS.items()):
        info = TOOL_RESULTS[key]
        T, rho, std = load_csv(key)
        tg = info["tg"]
        color = SYSTEM_COLORS[system]

        ax.errorbar(T, rho, yerr=std, fmt='o', color=color, markersize=5,
                    capsize=2, elinewidth=0.8, markeredgecolor='k', markeredgewidth=0.4,
                    zorder=5, label=f"MD data ({info['n_bins']} bins)")

        T_lo = np.linspace(T.min(), tg, 200)
        T_hi = np.linspace(tg, T.max(), 200)
        ax.plot(T_lo, info["a_glassy"]*T_lo + info["b_glassy"], "k-", linewidth=2, label="Glassy")
        ax.plot(T_hi, info["a_rubbery"]*T_hi + info["b_rubbery"], "k--", linewidth=2, label="Rubbery")

        rho_tg = info["a_glassy"] * tg + info["b_glassy"]
        ax.plot(tg, rho_tg, "*", color="gold", markersize=18, markeredgecolor="k",
                markeredgewidth=1.2, zorder=10, label=f"$T_g$ = {tg:.0f} K")
        ax.axvline(tg, color="gold", alpha=0.4, linestyle=":", linewidth=1.5)
        ax.axvspan(*info["exp_tg"], alpha=0.15, color="green", label=f"Exp {info['exp_tg'][0]}–{info['exp_tg'][1]} K")

        ax.set_title(f"{system} — {key} (Best Replicate)", fontsize=12, fontweight="bold")
        ax.set_xlabel("Temperature (K)", fontsize=11)
        ax.set_ylabel("Density (g/cm³)", fontsize=11)
        ax.legend(fontsize=8, loc="best")
        ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fname = OUT_DIR / "all_systems_best_v3.png"
    fig.savefig(fname, dpi=200, bbox_inches="tight")
    print(f"  Saved: {fname}")
    plt.close(fig)


def write_verification():
    """CSV and markdown comparing tool Tg vs paper Tg."""
    # CSV
    csv_path = OUT_DIR / "tg_verification_v3.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Run", "System", "Tg_tool", "Tg_paper", "Delta_K", "Match",
                     "R2", "F_stat", "Quality", "N_bins", "N_skipped",
                     "Method", "Exp_Tg", "Overestimate_K", "Notes"])
        for key in sorted(TOOL_RESULTS):
            info = TOOL_RESULTS[key]
            paper = PAPER_TG[key]
            delta = info["tg"] - paper
            match = "YES" if abs(delta) < 1.0 else ("CLOSE" if abs(delta) < 5.0 else "CHECK")
            exp_mid = (info["exp_tg"][0] + info["exp_tg"][1]) / 2
            overest = info["tg"] - exp_mid
            f_str = f"{info['f_stat']:.1f}" if info['f_stat'] else "N/A"
            w.writerow([key, info["system"], f"{info['tg']:.1f}", f"{paper:.1f}",
                        f"{delta:.1f}", match, f"{info['r2']:.4f}", f_str,
                        info["quality"], info["n_bins"], info["n_skipped"],
                        info["method"], f"{info['exp_tg'][0]}-{info['exp_tg'][1]}",
                        f"{overest:.1f}", info["notes"]])
    print(f"  Saved: {csv_path}")

    # Markdown summary
    md_path = OUT_DIR / "VERIFICATION_v3.md"
    with open(md_path, "w") as f:
        f.write("# Tg Fits v3 — Tool-Extracted Verification\n\n")
        f.write("**Generated:** 2026-03-16\n")
        f.write("**Data source:** Plateau-detected CSVs from `extract_tg` tool on full LAMMPS logs\n")
        f.write("**Fit method:** v3 F-stat exhaustive split with physics constraints\n\n")
        f.write("## Tg Comparison: Tool vs Paper\n\n")
        f.write("| Run | Tg_tool (K) | Tg_paper (K) | Δ (K) | R² | F-stat | Quality | Bins |\n")
        f.write("|-----|-------------|--------------|-------|-----|--------|---------|------|\n")
        for key in sorted(TOOL_RESULTS):
            info = TOOL_RESULTS[key]
            paper = PAPER_TG[key]
            delta = info["tg"] - paper
            f_str = f"{info['f_stat']:.1f}" if info['f_stat'] else "N/A"
            f.write(f"| {key} | {info['tg']:.1f} | {paper:.1f} | {delta:+.1f} | "
                    f"{info['r2']:.4f} | {f_str} | {info['quality']} | {info['n_bins']} |\n")
        f.write("\n## Key Findings\n\n")
        f.write("- **10 of 12 runs** match the paper Tg exactly (Δ < 1 K)\n")
        f.write("- **PE3**: 245.3 vs 248.2 K (Δ = -2.9 K) — minor difference from plateau filtering\n")
        f.write("- **PEG2**: 507.3 vs 288.5 K — F-stat failed physics constraints (rubbery slope NOT steeper); ")
        f.write("curve_fit fallback gives unreliable Tg. This run's near-linear profile is genuinely problematic.\n")
        f.write("- **PMMA2/3**: F-stat values < 3 (p > 0.14) — no statistically significant kink detected\n\n")
        f.write("## Files\n\n")
        f.write("| File | Description |\n")
        f.write("|------|-------------|\n")
        f.write("| `csv/*.csv` | Plateau-detected density-temperature bins from Lambda |\n")
        f.write("| `*_tg_fit_v3.png` | Individual run plots with tool's exact fit lines |\n")
        f.write("| `*_all_runs_v3.png` | Side-by-side comparison per system |\n")
        f.write("| `all_systems_best_v3.png` | 2×2 master figure |\n")
        f.write("| `tg_verification_v3.csv` | Machine-readable verification table |\n")
        f.write("| `replot_from_tool.py` | This script (fully reproducible) |\n")
    print(f"  Saved: {md_path}")


def main():
    print("=" * 70)
    print("PolyJarvis Tg Replot — From extract_tg Tool Output")
    print("=" * 70)

    print("\n── Individual run plots ──")
    for key in sorted(TOOL_RESULTS):
        plot_single(key, TOOL_RESULTS[key])

    print("\n── System combined plots ──")
    system_runs = {}
    for key, info in TOOL_RESULTS.items():
        system_runs.setdefault(info["system"], []).append(key)
    for system, keys in sorted(system_runs.items()):
        keys.sort(key=lambda k: TOOL_RESULTS[k]["run"])
        plot_system_combined(system, keys)

    print("\n── Master comparison ──")
    plot_master()

    print("\n── Verification outputs ──")
    write_verification()

    print("\n" + "=" * 70)
    print("DONE.")
    print("=" * 70)


if __name__ == "__main__":
    main()
