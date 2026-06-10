#!/usr/bin/env python3
"""
check_equilibration_comprehensive.py — Single-call polymer equilibration validator.

Runs all convergence and structural checks in one pass and returns:
  - overall_pass  (bool): True only when all hard-gate criteria are met
  - per-check details for thermo (A), chain conformation (B), spatial (C)
  - warnings list for soft flags that never block overall_pass
  - d05_markdown: ready-to-paste D-05 block for run_log.md

Hard gates (block overall_pass):
  A. Density drift, energy drift, density SEM, energy SEM
  B. Rg CV across chains (>30%)
  C. P2 nematic order (>0.10), density homogeneity voxel CV (>0.25)

Soft warnings (reported, never blocking):
  A. tau_eff / T_traj > 10%
  B. C_inf outside literature range, MSID slope deviation >20%, C(t) not decayed,
     MSD kinetic trap

Usage:
    python check_equilibration_comprehensive.py \
        --log_file /path/to/06_nvt_production.log \
        --dump_file /path/to/06_nvt_production.dump \
        --data_file /path/to/cell.data \
        --backbone_types 2 3 \
        [--output_dir /path/to/out] \
        [--skip_frames 50] \
        [--timestep_fs 1.0] \
        [--dump_every 1000] \
        [--n_backbone_bonds 118] \
        [--bond_length_A 1.54]
"""

import argparse
import json
import math
import sys
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import MDAnalysis as mda
import MDAnalysis.transformations as trans
from scipy import stats as sp_stats
from scipy.optimize import curve_fit
from scipy.special import gamma as sp_gamma

from analysis_utils import compute_tau_eff

warnings.filterwarnings("ignore", message="Reader has no dt information")
warnings.filterwarnings("ignore", category=UserWarning)


# ─── helpers ──────────────────────────────────────────────────────────────────

def to_native(obj):
    if isinstance(obj, dict):
        return {to_native(k): to_native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_native(x) for x in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


def r(x, n=4):
    return round(float(x), n)


# ─── Section A: Thermo convergence ───────────────────────────────────────────

def parse_lammps_log(path):
    """Parse all thermo tables from a LAMMPS log, return concatenated DataFrame."""
    import re
    all_dfs, header, rows = [], None, []
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
                if len(tokens) == len(header):
                    try:
                        rows.append([float(t) for t in tokens])
                        continue
                    except ValueError:
                        pass
                if rows:
                    all_dfs.append(pd.DataFrame(rows, columns=header))
                rows, header = [], None
    if rows and header is not None:
        all_dfs.append(pd.DataFrame(rows, columns=header))
    if not all_dfs:
        raise ValueError(f"No thermo data found in {path}")
    return pd.concat(all_dfs, ignore_index=True)


def _analyse_property(values, name, drift_threshold_pct, drift_pvalue, block_count):
    """Drift + block-average test for a single thermo property."""
    n = len(values)
    mean_val = float(np.mean(values))
    res = {"mean": r(mean_val, 6), "n_points": n}

    x = np.arange(n, dtype=float)
    slope, _, _, p_val, _ = sp_stats.linregress(x, values)
    total_drift = abs(slope * n)
    drift_pct = (total_drift / abs(mean_val) * 100) if abs(mean_val) > 1e-12 else 0.0
    d_pass = not (drift_pct > drift_threshold_pct and p_val < drift_pvalue)
    res["drift"] = {"pass": bool(d_pass), "drift_pct": r(drift_pct, 4), "p_value": r(p_val, 4)}

    bs = n // block_count
    if bs >= 2:
        bm = [float(np.mean(values[i * bs:(i + 1) * bs])) for i in range(block_count)]
        sem_b = float(np.std(bm, ddof=1) / math.sqrt(block_count))
        sem_pct = (sem_b / abs(mean_val) * 100) if abs(mean_val) > 1e-12 else 0.0
        b_pass = sem_pct < 1.0
    else:
        sem_pct, b_pass = 0.0, True
    res["block_sem"] = {"pass": bool(b_pass), "sem_pct": r(sem_pct, 4)}

    res["equilibrated"] = bool(d_pass and b_pass)
    return res


def check_thermo(log_file, eq_fraction, drift_threshold_pct, drift_pvalue, block_count,
                 temp_col, density_col, energy_col):
    df = parse_lammps_log(log_file)
    n_total = len(df)
    n_discard = int(n_total * (1 - eq_fraction))
    prod = df.iloc[n_discard:].reset_index(drop=True)
    n_prod = len(prod)

    if n_prod < 20:
        return {
            "error": f"Only {n_prod} production rows — need ≥20.",
            "equilibrated": False,
        }

    meta = {
        "n_total_rows": n_total,
        "n_production_rows": n_prod,
        "T_mean": r(float(prod[temp_col].mean()), 2) if temp_col in prod.columns else None,
    }

    results = {}
    for col, label in [(density_col, "density"), (energy_col, "energy")]:
        if col in prod.columns:
            results[label] = _analyse_property(
                prod[col].values, label, drift_threshold_pct, drift_pvalue, block_count
            )
        else:
            results[label] = {"error": f"Column '{col}' not found", "equilibrated": False}

    # tau_eff for density
    tau_eff_frac = None
    if density_col in prod.columns:
        tau_eff_frac = compute_tau_eff(prod[density_col].values)[1]
        results["density"]["tau_eff_fraction"] = r(tau_eff_frac, 4)

    density_ok = bool(results.get("density", {}).get("equilibrated", False))
    energy_ok = bool(results.get("energy", {}).get("equilibrated", False))

    is_npt = (
        "Volume" in prod.columns
        and prod["Volume"].mean() > 0
        and prod["Volume"].std() / prod["Volume"].mean() > 0.001
    )

    return {
        "equilibrated": bool(density_ok and energy_ok),
        "density": results.get("density"),
        "energy": results.get("energy"),
        "tau_eff_density_fraction": tau_eff_frac,
        "is_npt": is_npt,
        "meta": meta,
    }


# ─── Section B: Chain conformation ───────────────────────────────────────────

def _mass_weighted_rg_sq(positions, masses):
    total = masses.sum()
    r_cm = (masses[:, None] * positions).sum(axis=0) / total
    delta = positions - r_cm
    return float((masses * (delta ** 2).sum(axis=1)).sum() / total)


def _backbone_atoms_sorted(chain, backbone_set):
    """Return positions and indices of backbone atoms, sorted by atom index."""
    try:
        types = np.array([int(t) for t in chain.types])
    except Exception:
        return None, None
    mask = np.isin(types, list(backbone_set))
    if mask.sum() < 2:
        return None, None
    bb_atoms = chain.atoms[mask]
    order = np.argsort(bb_atoms.indices)
    return bb_atoms.positions[order], bb_atoms.indices[order]


def _saupe_p2(bond_vectors):
    if len(bond_vectors) == 0:
        return 0.0
    u = bond_vectors / (np.linalg.norm(bond_vectors, axis=1, keepdims=True) + 1e-12)
    Q = (3 * np.einsum("ni,nj->ij", u, u) - np.eye(3) * len(u)) / (2 * len(u))
    return float(np.linalg.eigvalsh(Q).max())


def _compute_density_cv(positions, masses, box_lengths, grid_n):
    pos = positions % box_lengths[np.newaxis, :]
    voxel_vol = np.prod(box_lengths) / grid_n ** 3
    idx = np.floor(pos / box_lengths[np.newaxis, :] * grid_n).astype(int)
    idx = np.clip(idx, 0, grid_n - 1)
    flat_idx = idx[:, 0] * grid_n * grid_n + idx[:, 1] * grid_n + idx[:, 2]
    voxel_mass = np.bincount(flat_idx, weights=masses, minlength=grid_n ** 3)
    voxel_density = voxel_mass / voxel_vol
    occ = voxel_density[voxel_density > 0]
    if len(occ) == 0:
        return 0.0, 0
    return float(occ.std() / occ.mean()) if occ.mean() > 0 else 0.0, len(occ)


def _fit_power_law(x, y, min_pts=5):
    mask = (x > 0) & (y > 0)
    if mask.sum() < min_pts:
        return None, None, None
    lx, ly = np.log(x[mask].astype(float)), np.log(y[mask])
    c = np.polyfit(lx, ly, 1)
    yp = np.polyval(c, lx)
    ss_res = ((ly - yp) ** 2).sum()
    ss_tot = ((ly - ly.mean()) ** 2).sum()
    r2 = float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    return float(c[0]), float(np.exp(c[1])), r2


def _kww_fit(lags_ps, ct_values):
    """Fit C(t) = exp(-(t/tau)^beta). Returns tau, beta, tau_relax, decay_fraction."""
    valid = ct_values > 0.01
    if valid.sum() < 5:
        return None, None, None, float(ct_values[-1]) if len(ct_values) else 0.0

    def kww(t, tau, beta):
        return np.exp(-((t / tau) ** beta))

    try:
        p0 = [float(lags_ps[valid][len(lags_ps[valid]) // 2]), 0.6]
        bounds = ([1e-3, 0.1], [1e9, 1.0])
        popt, _ = curve_fit(kww, lags_ps[valid], ct_values[valid], p0=p0,
                            bounds=bounds, maxfev=5000)
        tau, beta = float(popt[0]), float(popt[1])
        tau_relax = tau * sp_gamma(1.0 / beta) / beta
        decay_frac = float(1.0 - kww(lags_ps[-1], tau, beta))
        return tau, beta, float(tau_relax), decay_frac
    except Exception:
        return None, None, None, float(ct_values[-1]) if len(ct_values) else 0.0


def run_structural_analysis(u, chain_ids, backbone_set, n_atoms, skip_frames,
                            n_backbone_bonds, bond_length_A, timestep_fs, dump_every,
                            grid_n, trajectory_slice):
    """Single-pass over dump frames. Returns raw per-frame arrays for all checks."""
    # Storage
    rg_sq_per_frame = []   # (n_frames, n_chains)
    ree_per_frame = []     # (n_frames, n_chains, 3)  — end-to-end vectors
    com_per_frame = []     # (n_frames, n_chains, 3)  — CoMs for MSD
    p2_per_frame = []
    cv_per_frame = []
    msid_accum = None      # shape (n_backbone_per_chain - 1,)
    msid_n = None
    msid_count = 0

    try:
        masses_all = u.atoms.masses.copy()
    except Exception:
        masses_all = np.ones(n_atoms)

    # Precompute chain slices and backbone indices (constant across frames)
    chain_data = {}
    for cid in chain_ids:
        ch = u.select_atoms(f"resid {cid}")
        try:
            masses = ch.masses
        except Exception:
            masses = np.ones(ch.n_atoms)
        bb_pos, bb_ix = _backbone_atoms_sorted(ch, backbone_set)
        chain_data[cid] = {"sel": ch, "masses": masses, "bb_ix": bb_ix,
                           "has_bb": bb_pos is not None}

    # Initialise MSID accumulator
    first_bb_len = None
    for cid in chain_ids:
        if chain_data[cid]["has_bb"]:
            first_bb_len = len(chain_data[cid]["bb_ix"])
            break
    if first_bb_len is not None and first_bb_len >= 4:
        max_n = first_bb_len // 2
        msid_accum = np.zeros(max_n - 1)  # n = 2..max_n
        msid_count_arr = np.zeros(max_n - 1, dtype=int)
        msid_n_vals = np.arange(2, max_n + 1)
    else:
        msid_n_vals = None

    frame_idx = 0
    for ts in trajectory_slice:
        box = ts.dimensions[:3]

        rg_sq_row, ree_row, com_row = [], [], []
        bb_bond_vecs_all = []

        for cid in chain_ids:
            d = chain_data[cid]
            ch = d["sel"]
            masses = d["masses"]
            pos = ch.positions

            # Rg
            rg_sq = _mass_weighted_rg_sq(pos, masses)
            rg_sq_row.append(rg_sq)

            # CoM for MSD
            total = masses.sum()
            com = (masses[:, None] * pos).sum(axis=0) / total
            com_row.append(com)

            # End-to-end vector (from sorted backbone termini)
            if d["has_bb"]:
                bb_pos_now = ch.positions[
                    np.searchsorted(ch.atoms.indices, d["bb_ix"])
                    if hasattr(ch, "atoms") else np.arange(len(d["bb_ix"]))
                ]
                # Re-fetch backbone positions in sorted order
                bb_atoms = ch.atoms[np.isin(ch.atoms.indices, d["bb_ix"])]
                srt = np.argsort(bb_atoms.indices)
                bb_pos_sorted = bb_atoms.positions[srt]
                R = bb_pos_sorted[-1] - bb_pos_sorted[0]
                ree_row.append(R)

                # Backbone bond vectors for P2
                for i in range(len(bb_pos_sorted) - 1):
                    dr = bb_pos_sorted[i + 1] - bb_pos_sorted[i]
                    bb_bond_vecs_all.append(dr)

                # MSID accumulation
                if msid_n_vals is not None and len(bb_pos_sorted) == first_bb_len:
                    for j, sep in enumerate(msid_n_vals):
                        pairs = bb_pos_sorted[sep:] - bb_pos_sorted[:-sep]
                        msid_accum[j] += float((pairs ** 2).sum(axis=1).mean())
                        msid_count_arr[j] += 1
            else:
                ree_row.append(np.zeros(3))

        rg_sq_per_frame.append(rg_sq_row)
        ree_per_frame.append(ree_row)
        com_per_frame.append(com_row)

        # P2
        if bb_bond_vecs_all:
            p2_per_frame.append(_saupe_p2(np.array(bb_bond_vecs_all)))
        else:
            p2_per_frame.append(0.0)

        # Density homogeneity
        cv_val, _ = _compute_density_cv(u.atoms.positions.copy(), masses_all, box, grid_n)
        cv_per_frame.append(cv_val)

        frame_idx += 1
        if frame_idx % 100 == 0:
            print(f"  frame {frame_idx}", flush=True)

    rg_sq_arr = np.array(rg_sq_per_frame)   # (n_frames, n_chains)
    ree_arr = np.array(ree_per_frame)        # (n_frames, n_chains, 3)
    com_arr = np.array(com_per_frame)        # (n_frames, n_chains, 3)
    p2_arr = np.array(p2_per_frame)
    cv_arr = np.array(cv_per_frame)
    n_frames = frame_idx

    # ── Rg ──
    chain_mean_rg = np.sqrt(rg_sq_arr).mean(axis=0)  # per chain, mean over frames
    overall_mean_rg2 = float(rg_sq_arr.mean())
    overall_mean_rg = float(np.sqrt(rg_sq_arr).mean())
    rg_cv = float(np.std(chain_mean_rg) / np.mean(chain_mean_rg)) if len(chain_mean_rg) > 1 else 0.0
    rg_spread_flag = rg_cv > 0.30

    c_inf = None
    if n_backbone_bonds is not None and bond_length_A > 0:
        c_inf = float(6.0 * overall_mean_rg2 / (n_backbone_bonds * bond_length_A ** 2))

    rg_result = {
        "pass": bool(not rg_spread_flag),
        "cv": r(rg_cv, 4),
        "mean_Rg_A": r(overall_mean_rg, 3),
        "mean_Rg2_A2": r(overall_mean_rg2, 3),
        "rg_spread_flag": rg_spread_flag,
        "C_inf": r(c_inf, 3) if c_inf is not None else None,
        "n_chains": len(chain_ids),
        "frames_analysed": n_frames,
    }

    # ── MSID ──
    msid_result = {"available": False}
    if msid_n_vals is not None and msid_count_arr[0] > 0:
        msid_mean = msid_accum / msid_count_arr
        slope, _, r2 = _fit_power_law(msid_n_vals.astype(float), msid_mean)
        gaussian_pass = (slope is not None and abs(slope - 1.0) <= 0.20)
        msid_result = {
            "available": True,
            "slope": r(slope, 3) if slope is not None else None,
            "r2": r(r2, 4) if r2 is not None else None,
            "gaussian_pass": bool(gaussian_pass),
            "n_separations": int(len(msid_n_vals)),
        }

    # ── C(t) end-to-end autocorrelation ──
    ct_result = {"available": False}
    if ree_arr.shape[0] >= 10 and not np.allclose(ree_arr, 0):
        norms = np.linalg.norm(ree_arr, axis=-1, keepdims=True)
        ree_hat = np.where(norms > 1e-6, ree_arr / norms, 0.0)  # (n_frames, n_chains, 3)
        # Autocorrelation via overlapping windows (average over chains and origins)
        max_lag = n_frames // 2
        ct_lags = np.arange(1, max_lag + 1)
        ct_vals = np.zeros(max_lag)
        for lag in range(1, max_lag + 1):
            ct_vals[lag - 1] = float(
                np.einsum("fci,fci->", ree_hat[lag:], ree_hat[:n_frames - lag])
                / (ree_hat[:n_frames - lag].shape[0] * len(chain_ids))
            )
        # Convert lags to ps
        dt_ps = timestep_fs * dump_every / 1000.0
        lags_ps = ct_lags * dt_ps

        tau, beta, tau_relax, decay_frac_undecayed = _kww_fit(lags_ps, ct_vals)
        decay_fraction = float(1.0 - ct_vals[-1]) if len(ct_vals) > 0 else 0.0
        ct_result = {
            "available": True,
            "tau_relax_ps": r(tau_relax, 1) if tau_relax is not None else None,
            "tau_ps": r(tau, 1) if tau is not None else None,
            "beta": r(beta, 3) if beta is not None else None,
            "decay_fraction_at_end": r(decay_fraction, 3),
            "trajectory_ps": r(float(n_frames * dt_ps), 1),
            # True when no gate requested (ct_min_decay=None) or decay meets threshold
            "pass": True if args.ct_min_decay is None else bool(decay_fraction >= args.ct_min_decay),
        }

    # ── MSD ──
    max_lag_msd = n_frames // 2
    msd_lags = np.arange(1, max_lag_msd + 1)
    msd_vals = np.array([
        float(((com_arr[lag:] - com_arr[:n_frames - lag]) ** 2)
              .sum(axis=-1).mean())
        for lag in msd_lags
    ])
    alpha, _, alpha_r2 = _fit_power_law(msd_lags.astype(float), msd_vals)
    msd_max = float(msd_vals.max()) if len(msd_vals) > 0 else 0.0
    kinetic_trap = bool(msd_max < overall_mean_rg2) if overall_mean_rg2 > 0 else False

    if alpha is not None:
        if alpha < 0.4:
            regime = "sub-diffusive / kinetically trapped"
        elif alpha < 0.85:
            regime = "sub-diffusive (Rouse/reptation)"
        elif alpha < 1.15:
            regime = "Fickian diffusion"
        else:
            regime = "super-diffusive (non-equilibrated)"
    else:
        regime = "insufficient data"

    msd_result = {
        "alpha": r(alpha, 3) if alpha is not None else None,
        "alpha_r2": r(alpha_r2, 4) if alpha_r2 is not None else None,
        "diffusion_regime": regime,
        "msd_max_A2": r(msd_max, 2),
        "kinetic_trap_flag": kinetic_trap,
    }

    # ── P2 ──
    p2_mean = float(p2_arr.mean())
    p2_std = float(p2_arr.std())
    ordered_flag = p2_mean > 0.10
    p2_result = {
        "pass": bool(not ordered_flag),
        "p2_mean": r(p2_mean, 4),
        "p2_std": r(p2_std, 4),
        "p2_max": r(float(p2_arr.max()), 4),
        "ordered_flag": ordered_flag,
    }

    # ── Density homogeneity ──
    cv_mean = float(cv_arr.mean())
    atoms_per_voxel = n_atoms / grid_n ** 3
    poisson_cv = float(1.0 / math.sqrt(atoms_per_voxel)) if atoms_per_voxel > 0 else 1.0
    poisson_limited = poisson_cv > 0.30
    heterogeneous_flag = cv_mean > 0.25 and not poisson_limited
    dh_result = {
        "pass": bool(not heterogeneous_flag),
        "cv_mean": r(cv_mean, 4),
        "cv_max": r(float(cv_arr.max()), 4),
        "grid_n": grid_n,
        "atoms_per_voxel": r(atoms_per_voxel, 1),
        "poisson_cv": r(poisson_cv, 3),
        "poisson_limited": poisson_limited,
        "heterogeneous_flag": heterogeneous_flag,
    }

    return {
        "rg": rg_result,
        "msid": msid_result,
        "ct": ct_result,
        "msd": msd_result,
        "p2": p2_result,
        "density_homogeneity": dh_result,
    }


# ─── Build D-05 markdown block ────────────────────────────────────────────────

def build_d05_markdown(thermo, structural, warnings_list, overall_pass, timestamp, n_frames, skip_frames):
    verdict = "PASS" if overall_pass else "FAIL"
    lines = [
        f"## D-05 CONVERGENCE DETAIL",
        f"`check_equilibration_comprehensive` · T={thermo['meta'].get('T_mean', '?')} K · "
        f"{n_frames} frames analysed (skip={skip_frames}) · {timestamp}",
        "",
        f"**Overall: {verdict}**",
        "",
        "### A. Thermo convergence",
        "| Check | Value | Threshold | Result |",
        "|-------|-------|-----------|--------|",
    ]

    def _gate(b):
        return "PASS" if b else "FAIL"

    d = thermo.get("density", {})
    e = thermo.get("energy", {})
    is_npt = thermo.get("is_npt", False)

    dd = d.get("drift", {})
    density_drift_result = _gate(dd.get('pass', False)) if is_npt else "N/A (NVT — fixed volume)"
    lines.append(f"| Density drift | {dd.get('drift_pct','?')}% (p={dd.get('p_value','?')}) | <1%, p<0.01 | {density_drift_result} |")
    ed = e.get("drift", {})
    lines.append(f"| Energy drift | {ed.get('drift_pct','?')}% (p={ed.get('p_value','?')}) | <1%, p<0.01 | {_gate(ed.get('pass',False))} |")
    db = d.get("block_sem", {})
    density_sem_result = _gate(db.get('pass', False)) if is_npt else "N/A (NVT — fixed volume)"
    lines.append(f"| Density block-SEM | {db.get('sem_pct','?')}% | <1% | {density_sem_result} |")
    eb = e.get("block_sem", {})
    lines.append(f"| Energy block-SEM | {eb.get('sem_pct','?')}% | <1% | {_gate(eb.get('pass',False))} |")
    tau_frac = thermo.get("tau_eff_density_fraction")
    if tau_frac is not None:
        tau_pct = r(tau_frac * 100, 1)
        status = "⚠ long" if tau_frac > 0.10 else "OK"
        lines.append(f"| τ_eff density | {tau_pct}% of trajectory | — | {status} |")

    lines += ["", "### B. Chain conformation",
              "| Check | Value | Threshold | Result |",
              "|-------|-------|-----------|--------|"]

    rg = structural.get("rg", {})
    lines.append(f"| Rg CV (chain–chain) | {rg.get('cv','?'):.1%} | <30% | {_gate(rg.get('pass',False))} |")

    c_inf = rg.get("C_inf")
    if c_inf is not None:
        lines.append(f"| C∞ | {c_inf} | lit. varies | INFO |")

    msid = structural.get("msid", {})
    if msid.get("available"):
        slope = msid.get("slope")
        r2 = msid.get("r2")
        g_pass = msid.get("gaussian_pass", True)
        label = "OK" if g_pass else "⚠ non-Gaussian"
        lines.append(f"| MSID slope | {slope} (R²={r2}) | 1.0 ±20% | {label} |")
    else:
        lines.append("| MSID slope | — | 1.0 ±20% | skipped (short backbone) |")

    ct = structural.get("ct", {})
    if ct.get("available"):
        tau_r = ct.get("tau_relax_ps")
        dec = ct.get("decay_fraction_at_end", 0.0)
        label = "⚠ partial" if dec < 0.9 else "OK"
        lines.append(f"| C(t) τ_relax | {tau_r} ps ({dec:.0%} decayed) | — | {label} |")
    else:
        lines.append("| C(t) τ_relax | — | — | insufficient frames |")

    msd = structural.get("msd", {})
    trap = msd.get("kinetic_trap_flag", False)
    alpha = msd.get("alpha")
    msd_max = msd.get("msd_max_A2")
    rg2 = rg.get("mean_Rg2_A2")
    label = "⚠ trapped" if trap else "OK"
    lines.append(f"| MSD kinetic trap | {'yes' if trap else 'no'} (α={alpha}, MSD={msd_max} Å²{'>>Rg²='+str(rg2) if rg2 else ''}) | — | {label} |")

    lines += ["", "### C. Spatial / packing",
              "| Check | Value | Threshold | Result |",
              "|-------|-------|-----------|--------|"]

    p2 = structural.get("p2", {})
    lines.append(f"| P2 nematic order | {p2.get('p2_mean','?')} ± {p2.get('p2_std','?')} | <0.10 | {_gate(p2.get('pass',False))} |")

    dh = structural.get("density_homogeneity", {})
    grid_n = dh.get("grid_n")
    cv = dh.get("cv_mean")
    apv = dh.get("atoms_per_voxel")
    note = " (Poisson-limited — use caution)" if dh.get("poisson_limited") else ""
    lines.append(f"| Density homogeneity CV | {cv:.1%} ({grid_n}³ grid, {apv} atoms/voxel{note}) | <25% | {_gate(dh.get('pass',False))} |")

    if warnings_list:
        lines.append("")
        lines.append("**Warnings:** " + "; ".join(warnings_list))

    return "\n".join(lines)


# ─── Collect warnings ─────────────────────────────────────────────────────────

def collect_warnings(thermo, structural):
    w = []
    tau = thermo.get("tau_eff_density_fraction")
    if tau is not None and tau > 0.10:
        w.append(f"τ_eff = {tau*100:.1f}% of trajectory — short statistical sample; consider longer production run")

    c_inf = structural.get("rg", {}).get("C_inf")
    if c_inf is not None and (c_inf < 3.0 or c_inf > 15.0):
        w.append(f"C∞ = {c_inf} is outside broad expected range [3, 15] — verify backbone_types and n_backbone_bonds")

    msid = structural.get("msid", {})
    if msid.get("available") and not msid.get("gaussian_pass", True):
        slope = msid.get("slope")
        w.append(f"MSID slope = {slope} (expected 1.0 ±20% for Gaussian chain) — possible chain collapse or extension")

    ct = structural.get("ct", {})
    if ct.get("available"):
        dec = ct.get("decay_fraction_at_end", 1.0)
        tau_r = ct.get("tau_relax_ps")
        traj_ps = ct.get("trajectory_ps")
        if dec < 0.9:
            w.append(f"C(t) partially decayed: {dec:.0%} decayed at end of trajectory (τ_relax={tau_r} ps vs T_traj={traj_ps} ps)")

    if structural.get("msd", {}).get("kinetic_trap_flag"):
        w.append("MSD kinetic trap: chains have not displaced their own size (MSD_max < Rg²) — expected below Tg, problematic in melt state")

    return w


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Comprehensive polymer equilibration validator: thermo + structural checks in one call."
    )
    parser.add_argument("--log_file",          required=True)
    parser.add_argument("--dump_file",         required=True)
    parser.add_argument("--data_file",         required=True)
    parser.add_argument("--backbone_types",    type=int, nargs="+", required=True)
    parser.add_argument("--output_dir",        default=None)
    parser.add_argument("--graphs_dir",        default=None,
                        help="Directory for PNG figures (accepted for interface parity; currently unused).")
    parser.add_argument("--skip_frames",       type=int,   default=50)
    parser.add_argument("--timestep_fs",       type=float, default=1.0)
    parser.add_argument("--dump_every",        type=int,   default=1000)
    parser.add_argument("--n_backbone_bonds",  type=int,   default=None)
    parser.add_argument("--bond_length_A",     type=float, default=1.54)
    parser.add_argument("--eq_fraction",       type=float, default=0.5)
    parser.add_argument("--drift_threshold_pct", type=float, default=1.0)
    parser.add_argument("--drift_pvalue",      type=float, default=0.01)
    parser.add_argument("--block_count",       type=int,   default=10)
    parser.add_argument("--temp_col",          default="Temp")
    parser.add_argument("--density_col",       default="Density")
    parser.add_argument("--energy_col",        default="TotEng")
    parser.add_argument("--atom_style",        default="id resid type charge x y z")
    parser.add_argument("--ct_min_decay",      type=float, default=None,
                        help="Minimum C(t) decay fraction to pass hard gate (0–1). "
                             "Omit for soft-warning-only behaviour (backwards compat). "
                             "Use 0.25 for melt equilibration checks.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir) if args.output_dir else Path(args.dump_file).parent / "eq_comprehensive"
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    backbone_set = set(args.backbone_types)

    # ── Section A ──
    print("Section A: thermo convergence", flush=True)
    thermo = check_thermo(
        log_file=args.log_file,
        eq_fraction=args.eq_fraction,
        drift_threshold_pct=args.drift_threshold_pct,
        drift_pvalue=args.drift_pvalue,
        block_count=args.block_count,
        temp_col=args.temp_col,
        density_col=args.density_col,
        energy_col=args.energy_col,
    )
    if "error" in thermo:
        print(json.dumps({"status": "failed", "error": thermo["error"]}))
        sys.exit(0)

    # ── Section B + C ──
    print("Loading trajectory for structural checks...", flush=True)
    u = mda.Universe(args.data_file, args.dump_file,
                     format="LAMMPSDUMP", atom_style=args.atom_style)
    n_atoms = u.atoms.n_atoms
    n_frames_total = u.trajectory.n_frames
    print(f"  n_atoms={n_atoms}, n_frames={n_frames_total}", flush=True)

    chain_ids = sorted(set(int(r) for r in u.atoms.resids))
    print(f"  {len(chain_ids)} chains, backbone_types={args.backbone_types}", flush=True)

    try:
        u.trajectory.add_transformations(trans.unwrap(u.atoms))
        print("  Coordinate unwrapping applied", flush=True)
    except Exception as e:
        print(f"  WARNING: unwrap failed ({e})", flush=True)

    # Adaptive grid_n: target ~25 atoms/voxel, clamp [3, 10]
    grid_n = max(3, min(10, int(round((n_atoms / 25) ** (1 / 3)))))
    print(f"  Adaptive grid_n={grid_n} ({n_atoms/grid_n**3:.1f} atoms/voxel)", flush=True)

    # Try to auto-detect dump_every from timestep spacing
    dump_every = args.dump_every
    if n_frames_total >= 2:
        try:
            steps = []
            for ts in u.trajectory[:5]:
                steps.append(int(ts.data.get("step", -1)))
            if len(steps) >= 2 and steps[1] > steps[0] > 0:
                dump_every = steps[1] - steps[0]
                print(f"  Auto-detected dump_every={dump_every}", flush=True)
        except Exception:
            pass

    traj_slice = u.trajectory[args.skip_frames:]
    n_frames_used = n_frames_total - args.skip_frames

    if n_frames_used < 10:
        print(json.dumps({"status": "failed", "error": f"Only {n_frames_used} frames after skip — need ≥10."}))
        sys.exit(0)

    print(f"  Analysing {n_frames_used} frames (skip={args.skip_frames})", flush=True)
    structural = run_structural_analysis(
        u=u,
        chain_ids=chain_ids,
        backbone_set=backbone_set,
        n_atoms=n_atoms,
        skip_frames=args.skip_frames,
        n_backbone_bonds=args.n_backbone_bonds,
        bond_length_A=args.bond_length_A,
        timestep_fs=args.timestep_fs,
        dump_every=dump_every,
        grid_n=grid_n,
        trajectory_slice=traj_slice,
    )

    # ── overall_pass ──
    hard_checks = [
        thermo.get("density", {}).get("drift", {}).get("pass", False),
        thermo.get("energy", {}).get("drift", {}).get("pass", False),
        thermo.get("density", {}).get("block_sem", {}).get("pass", False),
        thermo.get("energy", {}).get("block_sem", {}).get("pass", False),
        structural["rg"].get("pass", False),
        structural["p2"].get("pass", False),
        structural["density_homogeneity"].get("pass", False),
        # C(t) gate — only active when --ct_min_decay supplied; defaults True otherwise
        structural.get("ct", {}).get("pass", True),
    ]
    overall_pass = all(hard_checks)

    warnings_list = collect_warnings(thermo, structural)

    d05 = build_d05_markdown(
        thermo=thermo, structural=structural,
        warnings_list=warnings_list,
        overall_pass=overall_pass,
        timestamp=timestamp,
        n_frames=n_frames_used,
        skip_frames=args.skip_frames,
    )

    result = to_native({
        "status": "success",
        "overall_pass": overall_pass,
        "thermo": {
            "equilibrated": thermo.get("equilibrated"),
            "density_drift": thermo.get("density", {}).get("drift"),
            "energy_drift": thermo.get("energy", {}).get("drift"),
            "density_sem": thermo.get("density", {}).get("block_sem"),
            "energy_sem": thermo.get("energy", {}).get("block_sem"),
            "tau_eff_density_fraction": thermo.get("tau_eff_density_fraction"),
            "meta": thermo.get("meta"),
        },
        "chain": {
            "rg": structural["rg"],
            "msid": structural["msid"],
            "ct": structural["ct"],
            "msd": structural["msd"],
        },
        "spatial": {
            "p2": structural["p2"],
            "density_homogeneity": structural["density_homogeneity"],
        },
        "warnings": warnings_list,
        "d05_markdown": d05,
        "log_file": args.log_file,
        "dump_file": args.dump_file,
        "data_file": args.data_file,
        "backbone_types": args.backbone_types,
        "timestamp": timestamp,
    })

    json_path = str(output_dir / "equilibration_comprehensive.json")
    with open(json_path, "w") as jf:
        json.dump(result, jf, indent=2)
    result["summary_json"] = json_path

    d05_path = str(output_dir / "d05_block.md")
    with open(d05_path, "w") as f:
        f.write(d05)
    result["d05_markdown_path"] = d05_path

    print(json.dumps(result))


if __name__ == "__main__":
    main()
