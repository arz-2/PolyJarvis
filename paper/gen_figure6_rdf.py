#!/usr/bin/env python3
"""Generate Figure 6: carbon-carbon radial distribution functions.

One panel per benchmark family (3x3). g(r) computed from a single equilibrated
300 K snapshot (the run's *_out.data) over all carbon atom types -- see
csv/<family>_rdf.csv produced by scratchpad/rdf_from_data.py. Single dense
snapshots (1000-8000 carbons) give smooth g(r): a sharp ~1.4-1.6 A bond peak and
convergence to g(r)=1, confirming homogeneous amorphous packing with no crystalline
order.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "csv")

POLYMERS = ["cis-PBD", "PE", "PEG", "PLA", "PMMA", "PS", "PSU", "PVC", "PEEK"]
COLORS = ["#4285F4", "#34A853", "#A142F4", "#00ACC1", "#EA4335",
          "#FB8C00", "#6D4C41", "#C0CA33", "#5E35B1"]

fig, axes = plt.subplots(3, 3, figsize=(9, 8), sharex=True)
axes = axes.ravel()

for ax, name, color in zip(axes, POLYMERS, COLORS):
    path = os.path.join(CSV, f"{name}_rdf.csv")
    r, g = [], []
    with open(path) as f:
        rd = csv.DictReader(f)
        for row in rd:
            r.append(float(row["r_A"])); g.append(float(row["g_r"]))
    r, g = np.array(r), np.array(g)

    ax.axhline(1.0, color="gray", lw=0.7, ls=":", zorder=1)
    ax.plot(r, g, color=color, lw=1.3, zorder=3)
    ax.set_title(name, fontsize=11, fontweight="bold")
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 5)
    # bond peak is clipped (g_max~8-18) to show medium-range structure; label it
    pk = int(np.argmax(g))
    ax.text(0.97, 0.93, f"bond peak {r[pk]:.2f} Å\n($g_{{max}}$={g[pk]:.0f})",
            transform=ax.transAxes, ha="right", va="top", fontsize=8, color=color)
    ax.tick_params(labelsize=9)

# shared labels
for ax in axes[6:]:
    ax.set_xlabel(r"$r$ (Å)".replace(r"Å", "Å"), fontsize=11)
for ax in axes[0::3]:
    ax.set_ylabel(r"$g(r)$", fontsize=11)

fig.tight_layout()
fig.savefig(os.path.join(HERE, "figures", "figure6_rdf.pdf"), dpi=300, bbox_inches="tight")
fig.savefig(os.path.join(HERE, "figures", "figure6_rdf.png"), dpi=300, bbox_inches="tight")
print("Saved figures/figure6_rdf.pdf and .png")
