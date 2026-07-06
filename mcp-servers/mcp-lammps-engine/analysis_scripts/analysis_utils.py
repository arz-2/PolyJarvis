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
