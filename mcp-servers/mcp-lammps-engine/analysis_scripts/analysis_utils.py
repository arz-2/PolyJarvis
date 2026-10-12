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


def parse_lammps_wall_time(path):
    """
    Parse the "Total wall time: H:MM:SS" footer LAMMPS writes on clean process exit.

    Returns the wall time in seconds (float), or None if the footer is absent -- a
    killed/crashed run (e.g. ENOSPC mid-write) never writes it, so callers needing a
    wall-time figure for every attempt must fall back to file-mtime diffing themselves.
    """
    pattern = re.compile(r'Total wall time:\s*(\d+):(\d{2}):(\d{2})')
    with open(path) as f:
        for line in f:
            m = pattern.search(line)
            if m:
                h, mm, ss = (int(x) for x in m.groups())
                return float(h * 3600 + mm * 60 + ss)
    return None


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


# ---------------------------------------------------------------------------
# Volume-fluctuation bulk modulus (moved here, not just imported, from
# extract_bulk_modulus.py: that module imports matplotlib at module scope, so it
# can't be cheaply imported in-process from orchestration -- see
# estimate_fluctuation_K_GPa below, which run_campaign.py calls before choosing a
# Murnaghan pressure ladder. extract_bulk_modulus.py re-exports this name so its
# own existing import (`from extract_bulk_modulus import compute_bulk_modulus`)
# keeps working unchanged.
# ---------------------------------------------------------------------------

_KB_SI = 1.380649e-23   # Boltzmann constant [J/K]
_A3_TO_M3 = 1e-30       # Å³ -> m³
_PA_TO_GPA = 1e-9       # Pa -> GPa
_PA_TO_ATM = 1.0 / 101325.0  # Pa -> atm


def compute_bulk_modulus(volumes, temperature):
    """
    Compute isothermal bulk modulus from volume time series.

    K_T = kB * T * <V> / Var(V)

    Args:
        volumes: array of instantaneous volumes (Å³)
        temperature: mean temperature (K)

    Returns:
        K_GPa (float), K_atm (float), meta (dict)
    """
    V_mean = np.mean(volumes)
    V_var = np.var(volumes, ddof=1)  # sample variance

    if V_var <= 0 or V_mean <= 0:
        return None, None, {"error": "Zero or negative volume variance"}

    K_Pa = _KB_SI * temperature * V_mean / V_var / _A3_TO_M3
    K_GPa = K_Pa * _PA_TO_GPA
    K_atm = K_Pa * _PA_TO_ATM
    beta_T = 1.0 / K_Pa  # [1/Pa]

    meta = {
        "V_mean_A3": float(V_mean),
        "V_std_A3": float(np.sqrt(V_var)),
        "V_var_A6": float(V_var),
        "T_mean_K": float(temperature),
        "K_Pa": float(K_Pa),
        "beta_T_per_Pa": float(beta_T),
    }

    return float(K_GPa), float(K_atm), meta


def estimate_fluctuation_K_GPa(npt_prod_log_path, eq_fraction=0.5):
    """Cheap, matplotlib-free volume-fluctuation K estimate from an ambient NPT
    production log -- callable in-process, before a Murnaghan pressure ladder is
    chosen (unlike compute_fluctuation_cross_check in
    extract_bulk_modulus_murnaghan.py, which only runs post-hoc, after the ladder
    already ran, as a cross-check against the completed fit).

    Never raises -- returns None on any missing/short/unreadable log or
    non-positive volume variance, matching compute_fluctuation_cross_check's own
    contract.
    """
    try:
        df = parse_lammps_log(npt_prod_log_path)
        vol_col = next((c for c in ["Volume", "Vol", "vol"] if c in df.columns), None)
        temp_col = next((c for c in ["Temp", "temp", "Temperature"] if c in df.columns), None)
        if vol_col is None or temp_col is None:
            return None
        n = len(df)
        prod = df.iloc[int(n * (1.0 - eq_fraction)):]
        if len(prod) < 50:
            return None
        K_GPa, _, _ = compute_bulk_modulus(prod[vol_col].to_numpy(dtype=float),
                                            float(prod[temp_col].mean()))
        return K_GPa
    except Exception:
        return None
