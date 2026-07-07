#!/usr/bin/env python3
"""Generate Figure 4: Bulk modulus box-and-whisker style chart.

Reference range shown as a shaded box per polymer.
Simulated individual runs as small dots, ensemble mean ± s.d. as large marker + error bar.
"""

import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

FIG_OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'figures')
os.makedirs(FIG_OUT, exist_ok=True)

# Data from data/property_comparison.md (reconciled 9-polymer EMC/PCFF benchmark,
# 2026-07-01 uniform gated-Murnaghan K update). Simulated K per replicate at 300 K
# is the single gated Murnaghan-EOS bulk modulus (fit_converged AND R2>=0.99 AND
# B0'∈[4,20]); volume fluctuation and uniaxial deformation are excluded cross-checks.
# All 36 replicates carry a gate-passing Murnaghan fit (PVC1/PEEK1 back-filled -> now
# 4 replicates each). Reference ranges are experimental isothermal K_T windows. PLA and
# PEEK have NO MD-comparable experimental K and are shown ungraded (sim points, no ref box).
polymers = ['cis-PBD', 'PE', 'PEG', 'PLA', 'PMMA', 'PS', 'PSU', 'PVC', 'PEEK']
colors   = ['#4285F4', '#34A853', '#A142F4', '#00ACC1', '#EA4335',
            '#FB8C00', '#6D4C41', '#C0CA33', '#5E35B1']

sim_runs = {
    'cis-PBD': [1.565, 1.606, 1.263, 1.600],
    'PE':      [1.463, 1.641, 1.358, 1.558],
    'PEG':     [3.394, 3.291, 3.337, 3.498],
    'PLA':     [4.984, 5.391, 4.462, 5.142],
    'PMMA':    [4.682, 4.800, 5.005, 4.458],
    'PS':      [2.725, 2.442, 2.531, 2.958],
    'PSU':     [4.427, 4.196, 4.417, 4.032],
    'PVC':     [2.852, 2.909, 2.804, 2.899],   # PVC1 back-filled -> 4 replicates
    'PEEK':    [5.157, 4.871, 5.306, 5.131],   # PEEK1 back-filled (wide-P rerun) -> 4 replicates
}

# Experimental isothermal K_T ranges (lower, upper). PLA/PEEK ungraded -> None.
ref_ranges = {
    'cis-PBD': (1.38, 1.38),   # cis-PBD's own K_T (PDH); the old 1.95 endpoint was cis-polyisoprene
    'PE':      (1.5, 2.0),
    'PEG':     (2.0, 2.5),
    'PLA':     None,           # no experimental bulk modulus
    'PMMA':    (3.5, 4.2),
    'PS':      (3.3, 4.0),
    'PSU':     (4.0, 5.5),
    'PVC':     (3.5, 4.5),
    'PEEK':    None,           # DAC measurement not comparable to small-strain K_T
}

ref_labels = {p: ('ungraded' if r is None else 'Exp.') for p, r in ref_ranges.items()}

fig, ax = plt.subplots(1, 1, figsize=(7.5, 4.5))

x_positions = np.arange(len(polymers))
box_width = 0.35

for i, (name, color) in enumerate(zip(polymers, colors)):
    x = x_positions[i]
    runs = np.array(sim_runs[name])
    mean = np.mean(runs)
    sd = np.std(runs, ddof=1)
    ref = ref_ranges[name]

    if ref is not None:
        ref_lo, ref_hi = ref
        ref_mid = (ref_lo + ref_hi) / 2

        # +/-30% acceptance band around the reference midpoint (the K pass/fail gate)
        gate_lo, gate_hi = ref_mid * 0.70, ref_mid * 1.30
        gate_w = box_width + 0.22
        ax.add_patch(mpatches.Rectangle(
            (x - gate_w/2, gate_lo), gate_w, gate_hi - gate_lo,
            facecolor='#9ecae1', edgecolor='none', zorder=0, alpha=0.30))

        # Reference range as shaded box
        rect = mpatches.FancyBboxPatch(
            (x - box_width/2, ref_lo), box_width, ref_hi - ref_lo,
            boxstyle="round,pad=0.02",
            facecolor='lightgray', edgecolor='#666666', linewidth=1.0,
            zorder=1, alpha=0.7
        )
        ax.add_patch(rect)

        # Horizontal line at reference midpoint
        ax.plot([x - box_width/2, x + box_width/2], [ref_mid, ref_mid],
                color='#666666', lw=0.8, ls='--', zorder=2)

    # Individual runs as small dots (jittered slightly), open markers if ungraded
    n = len(runs)
    jitter = np.linspace(-0.06, 0.06, n) if n > 1 else np.array([0.0])
    if ref is not None:
        ax.scatter(x + jitter, runs, s=35, color=color, alpha=0.5,
                   edgecolors='none', zorder=4)
    else:
        ax.scatter(x + jitter, runs, s=35, facecolors='none', edgecolors=color,
                   linewidths=1.2, alpha=0.8, zorder=4)

    # Ensemble mean ± s.d. — hollow diamond for ungraded
    fc = 'white' if ref is None else color
    ax.errorbar(x, mean, yerr=sd, fmt='D', color=color,
                markerfacecolor=fc, markersize=8,
                markeredgecolor=(color if ref is None else 'white'),
                markeredgewidth=1.2,
                capsize=5, elinewidth=2, capthick=1.5, zorder=5)


ax.set_xticks(x_positions)
ax.set_xticklabels(polymers, fontsize=10, rotation=20, ha='right')
ax.set_ylabel('Bulk Modulus (GPa)', fontsize=12)
ax.set_ylim(0, 6.4)
ax.set_xlim(-0.6, len(polymers) - 0.4)
ax.tick_params(axis='y', labelsize=10)
ax.tick_params(axis='x', length=0)

# Legend
gate_patch = mpatches.Patch(facecolor='#9ecae1', edgecolor='none',
                            alpha=0.30, label='±30% gate')
ref_patch = mpatches.Patch(facecolor='lightgray', edgecolor='#666666',
                           alpha=0.7, label='Exp. $K_T$ range')
sim_marker = ax.plot([], [], 'D', color='gray', markersize=7,
                     markeredgecolor='white', label='Simulated (mean ± s.d.)')[0]
run_marker = ax.scatter([], [], s=35, color='gray', alpha=0.5, label='Individual runs')
ung_marker = ax.plot([], [], 'D', color='gray', markerfacecolor='white',
                     markeredgecolor='gray', markersize=7,
                     label='Ungraded (no exp. $K$)')[0]
ax.legend(handles=[gate_patch, ref_patch, sim_marker, run_marker, ung_marker],
          loc='upper left', fontsize=8.5, framealpha=0.9)

ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
plt.savefig(os.path.join(FIG_OUT, 'figure5_bulk_modulus.pdf'), dpi=300, bbox_inches='tight')
plt.savefig(os.path.join(FIG_OUT, 'figure5_bulk_modulus.png'), dpi=300, bbox_inches='tight')
print("Saved figure5_bulk_modulus.pdf and .png")
