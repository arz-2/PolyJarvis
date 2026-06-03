#!/usr/bin/env python3
"""Shared statistical utilities for analysis scripts."""
import numpy as np


def compute_tau_eff(values):
    """
    Estimate autocorrelation time via batch-means plateau.
    Returns (tau_eff_frames, tau_eff_fraction).
    Flyvbjerg & Petersen, JCP 91, 461 (1989).
    """
    n = len(values)
    point_var = float(np.var(values, ddof=1))
    if point_var < 1e-30:
        return 0.0, 0.0
    inefficiencies = []
    b = 2
    while b <= n // 4:
        nb = n // b
        bm = [np.mean(values[i * b:(i + 1) * b]) for i in range(nb)]
        sem_sq = float(np.var(bm, ddof=1) / nb)
        inefficiencies.append(b * sem_sq / point_var)
        b *= 2
    if not inefficiencies:
        return 0.0, 0.0
    tau_frames = (float(np.mean(inefficiencies[-3:]))
                  if len(inefficiencies) >= 3 else float(inefficiencies[-1]))
    return tau_frames, tau_frames / n
