#!/usr/bin/env python3
"""Render manuscript figures from the generator outputs.

Reads gen/out/runs.json, gen/out/regrade_continuous.json and gen/references.json (through
tables.py's ref_values), plus each run's accepted thermal attempt for the Tg density bins and
branch fits. Writes PNG (300 dpi) and PDF into manuscript/figures/. Rerunnable without edits
after collect_runs.py / regrade_continuous.py pick up new runs.

Usage: mcp-servers/.venv/bin/python manuscript/gen/figures.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from statistics import mean, stdev

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Patch, Rectangle  # noqa: E402
import numpy as np  # noqa: E402

GEN = Path(__file__).resolve().parent
REPO = GEN.parents[1]
OUT = GEN / "out"
FIG = GEN.parent / "figures"
sys.path.insert(0, str(GEN))
from tables import REFS, ref_values  # noqa: E402

# Reference palette (dataviz skill, light mode). Slots 1-3 validate all-pairs.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
REF_FILL = "#d9d8d2"
REF_EDGE = "#9a9890"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]  # replicate 1, 2, 3
# One colour per polymer, shared by Figures 3-5 as in the round-1 figures.
PCOLOR = {"PE": "#34A853", "PEG": "#A142F4", "PLLA": "#00ACC1", "aPS": "#FB8C00",
          "sPVC": "#C0CA33", "PEEK": "#5E35B1", "PSU": "#6D4C41"}
STAR = "#f5c542"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": INK_2, "axes.labelcolor": INK,
    "xtick.color": INK_2, "ytick.color": INK_2, "axes.linewidth": 0.6, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "legend.frameon": False,
})


def load():
    runs = json.loads((OUT / "runs.json").read_text())["runs"]
    cont = json.loads((OUT / "regrade_continuous.json").read_text())["runs"]

    def verdict(r, st):
        return ((cont.get(r["run"], {}).get(st) or {}).get("verdict") or {}).get("verdict")

    for r in runs:
        r["_cell_ok"] = verdict(r, "equilibration") == "PASS" and verdict(r, "cooling") == "PASS"
        r["_tg_ok"] = verdict(r, "equilibration") == "PASS" and bool(r["tg"]["reportable"])
        r["_rep"] = int(r["run"].rsplit("_", 1)[1]) if r["run"].rsplit("_", 1)[1].isdigit() else 1
    systems = list(REFS["systems"])
    by = {s: sorted([r for r in runs if r["system"] == s], key=lambda r: r["run"]) for s in systems}
    return systems, by


def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / f"{name}.png", dpi=300, bbox_inches="tight")
    fig.savefig(FIG / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)


def style(ax):
    ax.grid(True, color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)


def marker(ax, x, y, color, ok, size=5, **kw):
    ax.plot([x], [y], "o", ms=size, mec=color, mfc=color if ok else SURFACE, mew=1.0, zorder=4, **kw)


# ------------------------------------------------------------------ Figure 3: density parity
def figure3(systems, by):
    """Parity of simulated against experimental density: one mean +- s.d. per system.

    Cells excluded by the convergence gate are not drawn (they are not part of the reported
    mean, and plotting them invited the reading that they were).
    """
    fig, ax = plt.subplots(figsize=(3.5, 3.4))
    style(ax)
    lo_all, hi_all = 0.8, 1.45
    xs = [lo_all, hi_all]
    ax.fill_between(xs, [x * 0.95 for x in xs], [x * 1.05 for x in xs], color=REF_FILL, alpha=0.6, lw=0, zorder=1)
    ax.plot(xs, xs, color=REF_EDGE, lw=0.8, zorder=2)
    for s in systems:
        vals = ref_values(s, "density")
        lo, hi = vals[0], vals[-1]
        mid = (lo + hi) / 2
        good = [r["density"]["rho_300K"] for r in by[s] if r["_cell_ok"]]
        m = mean(good)
        sd = stdev(good) if len(good) > 1 else 0.0
        c = PCOLOR[s]
        ax.plot([lo, hi], [m, m], color=INK_2, lw=2.2, solid_capstyle="round", zorder=3)
        ax.errorbar([mid], [m], yerr=[sd], fmt="none", ecolor=c, elinewidth=1.0, capsize=2, zorder=5)
        ax.plot([mid], [m], "o", ms=6, mec=SURFACE, mfc=c, mew=0.8, zorder=6)
        ax.annotate(s, (hi, m), xytext=(10, -3), textcoords="offset points", color=INK, fontsize=7)
    ax.set_xlim(lo_all, hi_all)
    ax.set_ylim(lo_all, hi_all)
    ax.set_aspect("equal")
    ax.set_xlabel(r"Experimental $\rho$ at 300 K (g cm$^{-3}$)")
    ax.set_ylabel(r"Simulated $\rho$ at 300 K (g cm$^{-3}$)")
    handles = [
        Line2D([], [], marker="o", ls="none", mfc=INK_2, mec=INK_2, ms=6, label="Mean ± s.d. (gate-passing cells)"),
        Line2D([], [], color=INK_2, lw=2.2, label="Experimental value or band"),
        Patch(color=REF_FILL, alpha=0.6, label="±5%"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=6.5)
    save(fig, "figure3_density_parity")


# ------------------------------------------------------------------ Figure 4: Tg curves
def thermal_for(run):
    d = REPO / "data" / run
    ws = json.loads((d / "workflow_state.json").read_text())
    a = ws["stages"]["thermal"]["accepted_attempt"]
    raw = d / "attempts" / "thermal" / a / "raw"
    re_dir = OUT / "tg_reextract" / run  # current extract_thermal.py fit, same staircase log
    src = re_dir if (re_dir / "thermal.json").exists() else raw
    t = json.loads((src / "thermal.json").read_text())
    bins = src / "tg_density_bins_plateau.csv"
    rows = list(csv.DictReader((bins if bins.exists() else raw / "tg_density_bins_plateau.csv").open()))
    T = [float(x["temperature"]) for x in rows]
    rho = [float(x["mean_density"]) for x in rows]
    return t, T, rho


def pool_sweeps(curves, step=5.0):
    """Replicate sweeps averaged on a common temperature grid (mean, s.d. per bin)."""
    allT = np.concatenate([np.asarray(T) for T, _ in curves])
    grid = np.arange(np.floor(allT.min() / step) * step, np.ceil(allT.max() / step) * step + 1, step)
    M = np.full((len(curves), len(grid)), np.nan)
    for i, (T, R) in enumerate(curves):
        for t_, r_ in zip(T, R):
            j = int(round((t_ - grid[0]) / step))
            if 0 <= j < len(grid):
                M[i, j] = r_
    n = np.sum(~np.isnan(M), axis=0)
    keep = n >= 1
    K = M[:, keep]
    with np.errstate(invalid="ignore"):
        m = np.nanmean(K, axis=0)
    sd = np.zeros(K.shape[1])
    multi = n[keep] >= 2
    if multi.any():
        sd[multi] = np.nanstd(K[:, multi], axis=0, ddof=1)
    return grid[keep], m, sd


def anchored_bilinear(T, rho, tg):
    """Continuous piecewise-linear fit with the knot fixed at tg (round-1 construction)."""
    dT = np.asarray(T) - tg
    X = np.column_stack([np.ones_like(dT), np.minimum(dT, 0.0), np.maximum(dT, 0.0)])
    coef, *_ = np.linalg.lstsq(X, np.asarray(rho), rcond=None)
    return coef  # c, a_glassy, a_rubbery


def figure4(systems, by):
    """Density against temperature, replicates pooled into one mean +- s.d. curve per system.

    Round-1 construction: the bilinear knot is fixed at the reported system-mean Tg, so the
    star sits on the kink by definition. Per-replicate overlays are not drawn.
    """
    fig, axes = plt.subplots(2, 4, figsize=(7.2, 4.0))
    for k, s in enumerate(systems):
        ax = axes.flat[k]
        style(ax)
        vals = ref_values(s, "tg_K")
        lo, hi = vals[0], vals[-1]
        pad = max(0.0, (6.0 - (hi - lo)) / 2)  # keep narrow bands and single values visible
        ax.axvspan(lo - pad, hi + pad, color=REF_FILL, alpha=0.9, lw=0, zorder=1)
        for edge in {lo, hi}:
            ax.axvline(edge, color=REF_EDGE, lw=0.6, zorder=1)
        c = PCOLOR[s]
        # Pool only the runs whose Tg fit is reportable -- the same runs the reported mean is
        # taken over. Including the others drags the pooled bend away from the mean Tg the
        # star is anchored at (aPS by 27 K, since aPS_2 and aPS_3 transition near 348 K).
        pooled_runs = [r for r in by[s] if r["_tg_ok"]] or list(by[s])
        curves = [(T, rho) for _, T, rho in (thermal_for(r["run"]) for r in pooled_runs)]
        grid, m, sd = pool_sweeps(curves)
        ax.errorbar(grid, m, yerr=sd, fmt="o", ms=2.4, color=c, ecolor=c, elinewidth=0.5,
                    capsize=1.0, mec=c, mfc=c, lw=0, zorder=4)
        tgs = [r["tg"]["Tg_K"] for r in by[s] if r["_tg_ok"]]
        if tgs:
            tg = mean(tgs)
            c0, a_g, a_r = anchored_bilinear(grid, m, tg)
            g = np.linspace(grid.min(), tg, 50)
            rb = np.linspace(tg, grid.max(), 50)
            ax.plot(g, c0 + a_g * (g - tg), color=INK_2, lw=0.9, zorder=5)
            ax.plot(rb, c0 + a_r * (rb - tg), color=INK_2, lw=0.9, ls=(0, (3, 1.5)), zorder=5)
            if len(tgs) > 1:
                ax.errorbar([tg], [c0], xerr=[stdev(tgs)], fmt="none", ecolor=INK_2,
                            elinewidth=0.8, capsize=2, zorder=6)
            ax.plot([tg], [c0], "*", ms=9, mfc=STAR, mec=INK, mew=0.4, zorder=7)
        ax.set_title(s, fontsize=8, color=INK, loc="left")
        ax.tick_params(labelsize=6.5)
        if k % 4 == 0:
            ax.set_ylabel(r"$\rho$ (g cm$^{-3}$)")
        if k >= 3:
            ax.set_xlabel("T (K)")
    leg = axes.flat[7]
    leg.axis("off")
    handles = [
        Line2D([], [], marker="o", ls="none", mfc=INK_2, mec=INK_2, ms=4, label="Replicate mean ± s.d."),
        Line2D([], [], color=INK_2, lw=0.9, label="Glassy branch"),
        Line2D([], [], color=INK_2, lw=0.9, ls=(0, (3, 1.5)), label="Rubbery branch"),
        Line2D([], [], marker="*", ls="none", mfc=STAR, mec=INK, ms=9, label=r"Mean $T_g$ (± s.d.)"),
        Patch(color=REF_FILL, label=r"Experimental $T_g$ (value or band)"),
    ]
    leg.legend(handles=handles, loc="center left", fontsize=6.5)
    fig.tight_layout(w_pad=0.8, h_pad=1.0)
    save(fig, "figure4_Tg_curves")


# ------------------------------------------------------------------ Figure 5: bulk modulus
def figure5(systems, by):
    """Bulk modulus per system: reference band, individual runs, and the mean +- s.d.

    Vertical as in round 1 (systems on x, K on y). Individual runs are jittered about the
    same x as their system's mean, so a run always sits over the marker it belongs to.
    """
    fig, ax = plt.subplots(figsize=(4.9, 3.4))
    style(ax)
    ax.grid(False, axis="x")
    for i, s in enumerate(systems):
        vals = ref_values(s, "K_GPa")
        c = PCOLOR[s]
        if vals is not None:
            lo, hi = vals[0], vals[-1]
            ax.add_patch(Rectangle((i - 0.36, lo * 0.7), 0.72, hi * 1.3 - lo * 0.7,
                                   facecolor=REF_FILL, alpha=0.55, lw=0, zorder=1))
            ax.add_patch(Rectangle((i - 0.24, lo), 0.48, max(hi - lo, 0.04),
                                   facecolor=REF_EDGE, alpha=0.8, lw=0, zorder=2))
        runs = [(r["K"]["K_GPa"], r["_cell_ok"]) for r in by[s]]
        jit = np.linspace(-0.17, 0.17, len(runs)) if len(runs) > 1 else np.array([0.0])
        for (kval, ok), dx in zip(runs, jit):
            ax.plot([i + dx], [kval], "o", ms=3.0, mec=c, mfc=c if ok else SURFACE, mew=0.9,
                    alpha=0.5 if ok else 0.9, zorder=3)
        good = [k for k, ok in runs if ok]
        m = mean(good)
        sd = stdev(good) if len(good) > 1 else 0.0
        graded = vals is not None
        ax.errorbar([i], [m], yerr=[sd], fmt="D", ms=7, color=c,
                    mfc=c if graded else SURFACE, mec=SURFACE if graded else c, mew=1.1,
                    elinewidth=1.3, capsize=3, zorder=6)
    ax.set_xticks(range(len(systems)))
    ax.set_xticklabels(systems, rotation=20, ha="right")
    ax.set_xlim(-0.6, len(systems) - 0.4)
    ax.set_ylim(0, 7)
    ax.set_ylabel(r"Bulk modulus $K$ at 300 K (GPa)")
    handles = [
        Line2D([], [], marker="D", ls="none", mfc=INK_2, mec=SURFACE, ms=6, label="Mean ± s.d. (gate-passing)"),
        Line2D([], [], marker="o", ls="none", mfc=INK_2, mec=INK_2, ms=3.0, alpha=0.5, label="Individual run"),
        Line2D([], [], marker="o", ls="none", mfc=SURFACE, mec=INK_2, ms=3.0, label="Excluded run"),
        Patch(color=REF_EDGE, alpha=0.8, label=r"Experimental $K_T$"),
        Patch(color=REF_FILL, alpha=0.55, label="±30%"),
    ]
    ax.legend(handles=handles, loc="upper left", fontsize=6, ncol=2, columnspacing=1.2, handlelength=1.6)
    save(fig, "figure5_bulk_modulus")


# ------------------------------------------------------------------ Figure 1: architecture
def figure1():
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 50)
    ax.axis("off")

    def box(x, y, w, h, text, fill=SURFACE, edge=INK_2, weight="normal", size=7):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2",
                                    fc=fill, ec=edge, lw=0.8))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=size, color=INK, weight=weight)

    def arrow(x0, y0, x1, y1, label=None, dy=1.2, style="-|>"):
        ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle=style, mutation_scale=8, color=INK_2, lw=0.8))
        if label:
            ax.text((x0 + x1) / 2, (y0 + y1) / 2 + dy, label, ha="center", fontsize=6, color=INK_2)

    agent = "#e8f0fa"
    box(1, 38, 17, 8, "Request\nSMILES + properties")
    box(24, 38, 20, 8, "Planning\nclassify · draft plan", fill=agent)
    box(50, 38, 21, 8, "Literature critic\n+ adjudicator", fill=agent)
    box(77, 38, 21, 8, "Validated\nrun_plan.json", weight="bold")
    arrow(18.5, 42, 23.5, 42)
    arrow(44.5, 42, 49.5, 42)
    arrow(71.5, 42, 76.5, 42)

    stages = ["build", "equilibration", "cooling", "thermal", "mechanical", "summary"]
    x0, w, gap = 3, 13.5, 2.6
    for i, st in enumerate(stages):
        box(x0 + i * (w + gap), 22, w, 7, st)
        if i:
            arrow(x0 + i * (w + gap) - gap + 0.3, 25.5, x0 + i * (w + gap) - 0.3, 25.5)
    ax.plot([87.5, 87.5, 9.75], [37.4, 33.6, 33.6], color=INK_2, lw=0.8)
    arrow(9.75, 33.6, 9.75, 29.8)
    ax.text(50, 34.6, "Deterministic stage scripts: code owns inputs, parameters, submission, provenance",
            ha="center", fontsize=6.5, color=INK_2)
    for i in (1, 2):
        cx = x0 + i * (w + gap) + w / 2
        ax.text(cx, 19.6, "gate", ha="center", fontsize=6, color=INK_2)

    box(14, 9, 72, 6.5, "Recovery agent: structured issues only, within a fixed decision budget",
        fill=agent, size=6.5)
    arrow(50, 21.3, 50, 16.2, style="<|-|>")
    box(1, 1, 98, 5, "MCP tool layer:  EMC cell builder   ·   LAMMPS engine + analysis   ·   molecule builder (RadonPy)",
        fill="#f1f0ec", size=6.5)
    for i in range(len(stages)):
        cx = x0 + i * (w + gap) + w / 2
        ax.plot([cx, cx], [21.6, 6.3], color=GRID, lw=0.6, zorder=0)
    handles = [Patch(fc=agent, ec=INK_2, label="Language-model step"), Patch(fc=SURFACE, ec=INK_2, label="Code")]
    ax.legend(handles=handles, loc="upper left", bbox_to_anchor=(0.0, 1.06), ncol=2, fontsize=6.5)
    save(fig, "figure1_architecture")


def main():
    systems, by = load()
    # Figure 1 is drawn by figure1_architecture.py, Figure 2 by figure2_trace.py.
    figure3(systems, by)
    figure4(systems, by)
    figure5(systems, by)
    for p in sorted(FIG.glob("figure*")):
        print(p.name)


if __name__ == "__main__":
    main()
