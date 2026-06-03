#!/usr/bin/env python3
"""Shared matplotlib style settings and save helper for PolyJarvis analysis plots."""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from pathlib import Path


def apply_style():
    plt.rcParams.update({
        'figure.figsize': (8, 5),
        'figure.dpi': 150,
        'axes.grid': True,
        'grid.alpha': 0.3,
        'axes.spines.top': False,
        'axes.spines.right': False,
        'axes.labelsize': 12,
        'axes.titlesize': 13,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'legend.fontsize': 10,
        'legend.framealpha': 0.8,
        'lines.linewidth': 1.5,
        'font.family': 'sans-serif',
    })


def save_fig(fig, path):
    """Save figure to path, creating parent dirs as needed, then close it."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, bbox_inches='tight', dpi=150)
    plt.close(fig)
