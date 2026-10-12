#!/usr/bin/env python3
"""Figure 2: a condensed, verbatim-faithful trace of one real run (PTFE_AI).

Same visual language as the round-1 conversation figure: a vertical stack of message blocks,
each with a coloured tag. Every line is taken from the run's own records:

  data/PTFE_AI/raw/run_plan.json               request and decided parameters
  data/PTFE_AI/raw/literature_grounding.json   critic verdict on the force field
  data/PTFE_AI/attempts/equilibration/attempt-0001/raw/equilibration.json   melt gate
  data/PTFE_AI/workflow_state.json             agent rationales (agent_escalations)
  data/PTFE_AI/attempts/thermal/attempt-0001/raw/thermal.json               Tg review
  data/PTFE_AI/attempts/summary/.../run_summary.json                        reported values

Agent text is shortened, not reworded beyond joining clauses; numbers are unchanged.
Output: manuscript/figures/figure2_conversation.{png,pdf}
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.font_manager import FontProperties  # noqa: E402

FIG = Path(__file__).resolve().parent.parent / "figures"

PAL = {
    "user":   dict(bg="#eef1f4", border="#aeb9c4", tag="#5a6b7b"),
    "code":   dict(bg="#f4f4f2", border="#c9c7c0", tag="#6b6a64"),
    "critic": dict(bg="#eaf1fb", border="#9dbce8", tag="#2c6fbb"),
    "tool":   dict(bg="#e9f5ec", border="#9ccfa6", tag="#2e8b57"),
    "decide": dict(bg="#fdf0e3", border="#f0c08a", tag="#e07b1a"),
    "human":  dict(bg="#f3eef8", border="#c4b1dc", tag="#6f4a9e"),
    "report": dict(bg="#faf6ef", border="#d8c4a0", tag="#8a6d3b"),
}
MONO = FontProperties(family="DejaVu Sans Mono")
SANS = FontProperties(family="DejaVu Sans")

FIG_W = 7.4
L_MARGIN = R_MARGIN = 0.28
TOP_MARGIN, BOT_MARGIN = 0.30, 0.22
BOX_W = FIG_W - L_MARGIN - R_MARGIN
TEXT_INSET = 0.20
LINE_H = 0.205
HEAD_H = 0.30
BODY_PAD = 0.10
GAP = 0.135
HEAD_FS, BODY_FS, TITLE_FS = 9.5, 8.6, 11.0

TITLE = "PTFE with the recovery agent: a validator defect found and escalated"
TRACE = [
    dict(kind="tool", tag="Melt gate", sub="equilibration · 700 K", mono=True, lines=[
        "density_homogeneity   FAIL   cv_signal 0.185 > 0.11  (floor 0.208, 24.2 atoms/voxel)",
        "other binding checks  PASS   drift 0.45%, n_eff 73, Rg CV 15%, P2 0.027, torsion",
        "auto-remedy           declined: no continuation length for this finding",
    ]),
    dict(kind="decide", tag="Recovery agent · end run", lines=[
        "Most likely a false positive of the density-homogeneity check on perfluorinated chemistry,",
        "not an unmixed melt. The floor assumes voxel mass comes from independent atoms; in PTFE 76%",
        "of the mass is F bonded to C, so the counting units are CF2 groups (floor 0.352 > measured",
        "CV 0.279). Every mixing indicator passes. No plan lever (chains, hold, seeds, time step,",
        "force field) changes the measured quantity. Close the run; the fix belongs in the checker,",
        "after which the melt can be regraded without new simulation.",
    ]),
    dict(kind="human", tag="Authors", lines=[
        "Revise the check: melt noise estimated from the two halves of the hold itself.",
        "Melt regraded and accepted; run resumed.  Cooling and the 300 K gate pass.",
    ]),
    dict(kind="report", tag="Result", mono=True, lines=[
        "Density   1.930 g/cm³ at 300 K     (melt 1.450 g/cm³ at 700 K)",
        "Bulk K    2.07 ± 0.05 GPa          Murnaghan, reportable",
        "Tg        withheld                 not resolved (TG_REVIEW)",
    ]),
]


def block_height(b):
    return HEAD_H + 2 * BODY_PAD + LINE_H * len(b["lines"])


def draw_block(ax, b, y_top):
    pal = PAL[b["kind"]]
    h = block_height(b)
    x0 = L_MARGIN
    ax.add_patch(mpatches.FancyBboxPatch((x0, y_top - h), BOX_W, h,
                                         boxstyle="round,pad=0.012,rounding_size=0.07",
                                         facecolor=pal["bg"], edgecolor=pal["border"], linewidth=1.1, zorder=1))
    ax.add_patch(mpatches.Rectangle((x0, y_top - h), 0.055, h, facecolor=pal["tag"], edgecolor="none", zorder=2))
    th, ty = 0.205, y_top - HEAD_H + 0.045
    tag_w = 0.118 * len(b["tag"]) + 0.30
    ax.add_patch(mpatches.FancyBboxPatch((x0 + TEXT_INSET - 0.09, ty), tag_w, th,
                                         boxstyle="round,pad=0.01,rounding_size=0.04",
                                         facecolor=pal["tag"], edgecolor="none", zorder=3))
    ax.text(x0 + TEXT_INSET, ty + th / 2, b["tag"], ha="left", va="center", fontsize=HEAD_FS,
            fontweight="bold", color="white", fontproperties=SANS, zorder=4)
    if b.get("sub"):
        ax.text(x0 + BOX_W - 0.14, ty + 0.103, b["sub"], ha="right", va="center", fontsize=8.0,
                color=pal["tag"], style="italic", fontproperties=SANS, zorder=4)
    fp = MONO if b.get("mono") else SANS
    yy = y_top - HEAD_H - BODY_PAD - LINE_H * 0.72
    for ln in b["lines"]:
        ax.text(x0 + TEXT_INSET, yy, ln, ha="left", va="center", fontsize=BODY_FS, color="#1c1c1c",
                fontproperties=fp, zorder=4)
        yy -= LINE_H
    return y_top - h - GAP


def build():
    title_band = 0.48
    total = title_band + TOP_MARGIN + BOT_MARGIN + sum(block_height(b) + GAP for b in TRACE)
    fig = plt.figure(figsize=(FIG_W, total))
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, FIG_W)
    ax.set_ylim(0, total)
    ax.set_aspect("equal")
    ax.axis("off")
    y = total - TOP_MARGIN
    ax.text(L_MARGIN, y - 0.16, TITLE, ha="left", va="top", fontsize=TITLE_FS, fontweight="bold",
            color="#222", fontproperties=SANS)
    y -= title_band
    for b in TRACE:
        y = draw_block(ax, b, y)
    FIG.mkdir(exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"figure2_conversation.{ext}", dpi=300, facecolor="white")
    print("wrote", FIG / "figure2_conversation.png")


if __name__ == "__main__":
    build()
