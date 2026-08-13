#!/usr/bin/env python3
"""Shared statistical utilities for analysis scripts."""
import re

import numpy as np
import pandas as pd


def parse_lammps_log(path):
    """
    Parse all thermo-output tables from a LAMMPS log file.
    Returns a single DataFrame with all rows concatenated.

    Rows whose token count is a multiple of the header width are split into
    chunks and all parsed — thermo rows that get concatenated onto one line
    (e.g. by buffered/interleaved writers) are recovered instead of silently
    ending the table.
    """
    all_dfs = []
    header = None
    rows = []
    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if re.match(r'^Step\s', line):
                if rows and header is not None:
                    all_dfs.append(pd.DataFrame(rows, columns=header))
                    rows = []
                header = line.split()
                continue
            if header is not None:
                tokens = line.split()
                n = len(header)
                if len(tokens) > 0 and len(tokens) % n == 0:
                    chunks = [tokens[i*n:(i+1)*n] for i in range(len(tokens) // n)]
                    try:
                        rows.extend([[float(t) for t in chunk] for chunk in chunks])
                        continue
                    except ValueError:
                        pass
                if rows:
                    all_dfs.append(pd.DataFrame(rows, columns=header))
                    rows = []
                    header = None
    if rows and header is not None:
        all_dfs.append(pd.DataFrame(rows, columns=header))
    if not all_dfs:
        raise ValueError(f"No thermo data found in {path}")
    return pd.concat(all_dfs, ignore_index=True)


def integrated_act(values):
    """
    Integrated autocorrelation time (frames) by summing the normalised ACF to its
    first zero crossing.  Returns (tau_frames, n_effective).

    tau is the statistical inefficiency s = 1 + 2*sum_k c(k): s == 1 means every
    frame is independent, so n_effective = n / s with NO further factor of 2.
    """
    x = np.asarray(values, dtype=float)
    n = len(x)
    if n < 2:
        return 1.0, float(n)
    x = x - x.mean()
    var = float(np.dot(x, x) / n)
    if var < 1e-30:
        return 1.0, float(n)
    tau = 1.0
    for k in range(1, n // 2):
        c = float(np.dot(x[:-k], x[k:]) / ((n - k) * var))
        if c <= 0:
            break
        tau += 2.0 * c
    tau = max(tau, 1.0)
    return tau, n / tau


def compute_tau_eff(values):
    """
    Autocorrelation time of a thermo series, as the integrated statistical
    inefficiency.  Returns (tau_eff_frames, tau_eff_fraction).

    Flyvbjerg & Petersen, JCP 91, 461 (1989) motivates the blocking view, but the
    blocking curve must be read at its PLATEAU.  Averaging its tail (largest block
    sizes, where the number of blocks falls to 4-8) reads the noisiest end and
    underestimates tau by 4-39x on this pipeline's own trajectories, so the
    integrated ACF is used directly instead.

    A flat series keeps the historical (0.0, 0.0) contract; otherwise tau >= 1.0.
    """
    n = len(values)
    if n < 2 or float(np.var(values, ddof=1)) < 1e-30:
        return 0.0, 0.0
    tau_frames, _ = integrated_act(values)
    return tau_frames, tau_frames / n


def effective_sample_size(n, tau_frames):
    """Independent-sample count for a series of n frames with inefficiency tau_frames."""
    return int(n / max(1.0, float(tau_frames)))
