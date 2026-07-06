#!/usr/bin/env python3
"""Generate Figure 3: Density parity plot (predicted vs experimental)."""

import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

FIG_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'figures')
os.makedirs(FIG_OUT, exist_ok=True)

# Data from data/property_comparison.md (reconciled 9-polymer EMC/PCFF benchmark,
# per-replicate density at 300 K; 4 replicates each).
data = {
    'cis-PBD': {'runs': [0.898, 0.898, 0.898, 0.899], 'ref': 0.900,  'color': '#4285F4'},
    'PE':      {'runs': [0.860, 0.859, 0.857, 0.862], 'ref': 0.855,  'color': '#34A853'},
    'PEG':     {'runs': [1.058, 1.058, 1.058, 1.061], 'ref': 1.12,   'color': '#A142F4'},
    'PLA':     {'runs': [1.229, 1.223, 1.220, 1.226], 'ref': 1.25,   'color': '#00ACC1'},
    'PMMA':    {'runs': [1.117, 1.122, 1.117, 1.111], 'ref': 1.19,   'color': '#EA4335'},
    'PS':      {'runs': [0.978, 0.974, 0.988, 0.987], 'ref': 1.05,   'color': '#FB8C00'},
    'PSU':     {'runs': [1.187, 1.185, 1.184, 1.179], 'ref': 1.24,   'color': '#6D4C41'},
    'PVC':     {'runs': [1.353, 1.349, 1.344, 1.350], 'ref': 1.38,   'color': '#C0CA33'},
    'PEEK':    {'runs': [1.193, 1.194, 1.199, 1.197], 'ref': 1.263,  'color': '#5E35B1'},
}

fig, ax = plt.subplots(1, 1, figsize=(5.5, 5.5))

# Parity line and ±5% band
lims = [0.82, 1.45]
x_line = np.linspace(lims[0], lims[1], 100)
ax.plot(x_line, x_line, 'k--', lw=1, label='Perfect agreement', zorder=1)
ax.fill_between(x_line, x_line * 0.95, x_line * 1.05, alpha=0.15, color='gray', label='±5%', zorder=0)

for name, d in data.items():
    runs = np.array(d['runs'])
    mean = np.mean(runs)
    sd = np.std(runs, ddof=1)
    ref = d['ref']
    c = d['color']

    # Individual runs (small markers)
    for r in runs:
        ax.scatter(ref, r, s=30, color=c, alpha=0.4, edgecolors='none', zorder=3)

    # Ensemble mean (large marker with error bar)
    ax.errorbar(ref, mean, yerr=sd, fmt='o', color=c, markersize=10,
                markeredgecolor='white', markeredgewidth=1, capsize=4,
                elinewidth=1.5, zorder=4, label=name)

ax.set_xlim(lims)
ax.set_ylim(lims)
ax.set_xlabel('Experimental Density (g/cm³)', fontsize=12)
ax.set_ylabel('Simulated Density (g/cm³)', fontsize=12)
ax.legend(loc='upper left', fontsize=8, framealpha=0.9, ncol=2)
ax.set_aspect('equal')
ax.tick_params(labelsize=10)

plt.tight_layout()
plt.savefig(os.path.join(FIG_OUT, 'figure4_density_parity.pdf'), dpi=300, bbox_inches='tight')
plt.savefig(os.path.join(FIG_OUT, 'figure4_density_parity.png'), dpi=300, bbox_inches='tight')
print("Saved figure4_density_parity.pdf and .png")
