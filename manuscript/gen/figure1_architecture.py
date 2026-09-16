#!/usr/bin/env python3
"""Figure 1: PolyJarvis architecture, in the visual language of the round-1 figure.

Code owns execution, so the large central box is the deterministic control plane; the two
language-model roles attach to it; the three MCP servers sit below.

Models are the ones recorded in the headless session transcripts of the runs (assistant
message `model` field): literature critic claude-sonnet-5 (pinned `model="sonnet"` in
orchestration/langgraph/nodes.py and .claude/agents/literature-grounding-worker.md),
adjudicator claude-opus-5, recovery agent claude-opus-5.

Output: manuscript/figures/figure1_architecture.{png,pdf}
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402
from matplotlib.patches import FancyArrowPatch  # noqa: E402

FIG = Path(__file__).resolve().parent.parent / "figures"
SANS = FontProperties(family="DejaVu Sans")

C = {
    "researcher": dict(bg="#dceafb", border="#5b8fd6", head="#2c5fa0"),
    "llm":        dict(bg="#fdf4e6", border="#e8a44e", head="#e07b1a"),
    "plane":      dict(bg="#f3f5f8", border="#8a9bb0", head="#4a5d75"),
    "emc":        dict(bg="#e6f4ea", border="#5aa873", head="#2e8b57"),
    "radon":      dict(bg="#e2f1ef", border="#4ca99a", head="#2f9e8e"),
    "lammps":     dict(bg="#efe7f7", border="#9a72c2", head="#7a3fb0"),
    "lane":       dict(bg="#fbfbfa", border="#d5dbe3"),
}
INK = "#1c1c1c"
SUB = "#5d5d5d"
FIG_W, FIG_H = 16.0, 9.9
BAR_H = 0.48


def box(ax, x, y, w, h, key, lw=1.3, z=2):
    ax.add_patch(mpatches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.01,rounding_size=0.06",
                                         facecolor=C[key]["bg"], edgecolor=C[key]["border"], linewidth=lw, zorder=z))


def header(ax, x, y, w, h, key, title, sub=None, fs=15):
    ax.add_patch(mpatches.FancyBboxPatch((x, y + h - BAR_H), w, BAR_H, boxstyle="round,pad=0.01,rounding_size=0.06",
                                         facecolor=C[key]["head"], edgecolor="none", zorder=3))
    ax.add_patch(mpatches.Rectangle((x, y + h - BAR_H), w, BAR_H * 0.5, facecolor=C[key]["head"],
                                    edgecolor="none", zorder=3))
    ax.text(x + w / 2, y + h - BAR_H / 2, title, ha="center", va="center", fontsize=fs, fontweight="bold",
            color="white", fontproperties=SANS, zorder=4)
    if sub:
        ax.text(x + w / 2, y + h - BAR_H - 0.2, sub, ha="center", va="center", fontsize=10.5,
                color=C[key]["head"], style="italic", fontproperties=SANS, zorder=4)
    return y + h - BAR_H


def arrow(ax, p0, p1, color="#5a6b7b", lw=1.9, ms=17, z=1):
    ax.add_patch(FancyArrowPatch(p0, p1, arrowstyle="-|>", mutation_scale=ms, lw=lw, color=color,
                                 shrinkA=2, shrinkB=2, zorder=z))


def label(ax, x, y, text, ha):
    ax.text(x, y, text, ha=ha, va="center", fontsize=10.5, color=SUB, fontproperties=SANS)


def build():
    fig = plt.figure(figsize=(FIG_W, FIG_H))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, FIG_W)
    ax.set_ylim(0, FIG_H)
    ax.set_aspect("equal")
    ax.axis("off")

    # system boundary (right of the researcher)
    sx, sy = 4.05, 0.3
    sw, sh = FIG_W - sx - 0.3, FIG_H - 0.6
    ax.add_patch(mpatches.FancyBboxPatch((sx, sy), sw, sh, boxstyle="round,pad=0.02,rounding_size=0.10",
                                         facecolor="none", edgecolor="#b8b8b8", linewidth=1.3,
                                         linestyle=(0, (6, 4)), zorder=0))
    ax.text(sx + sw - 0.18, sy + 0.16, "PolyJarvis", ha="right", va="bottom", fontsize=11.5, color="#9a9a9a",
            style="italic", fontproperties=SANS)
    ix0, ix1 = sx + 0.3, sx + sw - 0.3          # inner content span
    iw = ix1 - ix0

    # MCP servers (bottom)
    gap = 0.34
    srv_w = (iw - 2 * gap) / 3
    srv_y, srv_h = 0.75, 1.55
    # control plane (middle)
    py, ph = srv_y + srv_h + 0.7, 3.55
    # language-model roles (top)
    ly, lh = py + ph + 0.75, 1.85
    lw_ = (iw - 0.9) / 2

    # The two language-model roles, grouped and labelled as the LLM boundary. Drawn behind
    # the role boxes (zorder 1) and dashed like the PolyJarvis boundary, so it reads as a
    # grouping rather than a component of its own.
    gx0, gy0 = ix0 - 0.16, ly - 0.14
    gw, gh = iw + 0.32, lh + 0.48
    ax.add_patch(mpatches.FancyBboxPatch((gx0, gy0), gw, gh,
                                         boxstyle="round,pad=0.02,rounding_size=0.10",
                                         facecolor="#fffdf9", edgecolor=C["llm"]["border"],
                                         linewidth=1.3, linestyle=(0, (6, 4)), zorder=1))
    ax.text(gx0 + 0.20, gy0 + gh - 0.15, "LLM", ha="left", va="top", fontsize=12.5,
            color=C["llm"]["head"], style="italic", fontweight="bold", fontproperties=SANS,
            zorder=4)
    box(ax, ix0, ly, lw_, lh, "llm", lw=1.5)
    hb = header(ax, ix0, ly, lw_, lh, "llm", "Literature critic + adjudicator",
                "Claude Sonnet 5  ·  Claude Opus 5", fs=13.5)
    ax.text(ix0 + lw_ / 2, ly + (hb - 0.25 - ly) / 2 + 0.08, "Reviews the force-field decision against\n"
            "published MD studies; accepted overrides\nare re-validated like any plan edit",
            ha="center", va="center", fontsize=10.6, color=INK, fontproperties=SANS, linespacing=1.35, zorder=4)
    rx_llm = ix1 - lw_
    box(ax, rx_llm, ly, lw_, lh, "llm", lw=1.5)
    hb = header(ax, rx_llm, ly, lw_, lh, "llm", "Recovery agent", "Claude Opus 5", fs=13.5)
    ax.text(rx_llm + lw_ / 2, ly + (hb - 0.25 - ly) / 2 + 0.08, "Structured issues only, after deterministic\n"
            "remedies: retry, revise plan, end run, or\naccept with a property withheld",
            ha="center", va="center", fontsize=10.6, color=INK, fontproperties=SANS, linespacing=1.35, zorder=4)

    box(ax, ix0, py, iw, ph, "plane", lw=1.6)
    header(ax, ix0, py, iw, ph, "plane", "Deterministic control plane",
           "owns simulation inputs, parameters, job submission, validation, recovery limits, provenance")
    lane_x, lane_w, lane_y, lane_h = ix0 + 0.3, iw - 0.6, py + 0.2, ph - 1.05
    ax.add_patch(mpatches.FancyBboxPatch((lane_x, lane_y), lane_w, lane_h,
                                         boxstyle="round,pad=0.01,rounding_size=0.05",
                                         facecolor=C["lane"]["bg"], edgecolor=C["lane"]["border"],
                                         linewidth=1.0, zorder=2))
    lanes = [
        ("#6b6f87", "build",         "EMC packs the amorphous cell and assigns the force field; the cell is validated"),
        ("#2e8b57", "equilibration", "compression and annealing to a melt hold; the melt gate checks convergence"),
        ("#2c6fbb", "cooling",       "cools the melt to the target temperature; the assessment gate checks the cell"),
        ("#7a3fb0", "thermal",       "stepwise cooling from the melt; Tg from the density-temperature fit"),
        ("#b5651d", "mechanical",    "NPT pressure ladder on the cooled cell; bulk modulus from a Murnaghan fit"),
        ("#2f9e8e", "summary",       "collects properties, gate verdicts, and provenance for the run"),
    ]
    row_dy = (lane_h - 0.4) / (len(lanes) - 1)
    yy = lane_y + lane_h - 0.2
    for color, name, desc in lanes:
        ax.add_patch(mpatches.Rectangle((lane_x + 0.18, yy - 0.09), 0.12, 0.18, facecolor=color,
                                        edgecolor="none", zorder=4))
        ax.text(lane_x + 0.44, yy, f"{name}:", ha="left", va="center", fontsize=10.8, fontweight="bold",
                color=color, fontproperties=SANS, zorder=4)
        ax.text(lane_x + 2.2, yy, desc, ha="left", va="center", fontsize=10.8, color=INK,
                fontproperties=SANS, zorder=4)
        yy -= row_dy

    servers = [
        ("emc", "EMC Builder MCP", "cell builder",
         "Amorphous cells and typing:\nPCFF, OPLS-AA, TraPPE-UA"),
        ("radon", "RadonPy MCP", "classifier",
         "Backbone class (PoLyInfo\nscheme); molecule utilities"),
        ("lammps", "LAMMPS Engine MCP", "simulation and analysis",
         "Stage decks and job chains;\nconvergence checks; properties"),
    ]
    for i, (key, title, sub, desc) in enumerate(servers):
        x = ix0 + i * (srv_w + gap)
        box(ax, x, srv_y, srv_w, srv_h, key, lw=1.4)
        hb = header(ax, x, srv_y, srv_w, srv_h, key, title, sub, fs=14)
        ax.text(x + srv_w / 2, hb - 0.42, desc, ha="center", va="top", fontsize=10.4, color=INK,
                fontproperties=SANS, linespacing=1.35, zorder=4)
        mx = x + srv_w / 2
        arrow(ax, (mx - 0.12, py), (mx - 0.12, srv_y + srv_h), color="#8a8a8a")
        arrow(ax, (mx + 0.12, srv_y + srv_h), (mx + 0.12, py), color="#8a8a8a")

    top = py + ph
    for x0, down, up in ((ix0 + lw_ / 2, "drafted plan", "verdict, overrides"),
                         (rx_llm + lw_ / 2, "structured issue", "bounded decision")):
        arrow(ax, (x0 - 0.2, top), (x0 - 0.2, ly), color="#c98a3d")
        arrow(ax, (x0 + 0.2, ly), (x0 + 0.2, top), color="#c98a3d")
        label(ax, x0 - 0.35, (ly + top) / 2, down, "right")
        label(ax, x0 + 0.35, (ly + top) / 2, up, "left")

    # researcher (left), connected to the control plane
    rw, rh = 2.75, 1.75
    rx, rcy = 0.25, py + ph / 2
    ry = rcy - rh / 2
    box(ax, rx, ry, rw, rh, "researcher")
    hb = header(ax, rx, ry, rw, rh, "researcher", "Researcher", fs=14)
    ax.text(rx + rw / 2, (ry + hb) / 2, "Repeat-unit SMILES,\ntarget properties,\ncompute budget",
            ha="center", va="center", fontsize=11, color=INK, fontproperties=SANS, linespacing=1.35)
    arrow(ax, (rx + rw, rcy + 0.22), (ix0, rcy + 0.22), lw=2.6, ms=24)
    arrow(ax, (ix0, rcy - 0.22), (rx + rw, rcy - 0.22), lw=2.6, ms=24)
    label(ax, (rx + rw + sx) / 2, rcy + 0.5, "request", "center")
    label(ax, (rx + rw + sx) / 2, rcy - 0.5, "results", "center")

    FIG.mkdir(exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"figure1_architecture.{ext}", dpi=300, facecolor="white")
    print("wrote", FIG / "figure1_architecture.png")


if __name__ == "__main__":
    build()
