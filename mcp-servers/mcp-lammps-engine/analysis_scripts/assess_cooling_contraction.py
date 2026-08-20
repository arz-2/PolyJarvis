#!/usr/bin/env python3
"""
assess_cooling_contraction.py — self-consistency check for melt-to-glass cooling.

A converged 300 K density tells you the cell stopped moving — NOT that it stopped at a
physically reasonable value. A kinetically trapped (under-annealed) glass converges at a
too-low density because free volume is frozen in during cooling. This script detects that
purely from the run's OWN data: does the observed melt-to-glass density contraction match
what the system's own thermal-expansion coefficients predict?

    contraction_shortfall = actual_contraction / expected_contraction

where actual_contraction = rho_glass / rho_melt and expected_contraction is the volumetric
contraction implied by cooling from T_equil through Tg to 300 K along alpha_glass (below Tg)
and alpha_melt (above Tg). shortfall < 1 means the cell densified less on cooling than its
own thermal-expansion physics predicts -- i.e. free volume got frozen in.

This is deliberately NOT a comparison to any experimental/curated density or thermal-
expansion value -- a novel system may have neither. alpha_glass/alpha_melt default to
literature-typical-polymer constants (not specific to any one material) and the production
caller never overrides them from a class-curated value, so every system is assessed the
same way regardless of what (if anything) is known about it.

Usage:
    python assess_cooling_contraction.py \
        --melt_data  /path/npt_production_out.data \
        --glass_data /path/npt_prod300_out.data \
        --tg_K 378 --t_equil_K 550 \
        [--alpha_glass 2.5e-4] [--alpha_melt 6e-4]

Emits JSON to stdout: rho_melt, rho_glass, expected_contraction, actual_contraction,
contraction_shortfall, under_annealed_cooling, verdict, remedy, extrapolation_reliable,
markdown.
"""

import argparse
import json
import os
import sys

# LAMMPS data-file section headers (everything between them is body content).
SECTIONS = {
    'Masses', 'Atoms', 'Velocities', 'Bonds', 'Angles', 'Dihedrals', 'Impropers',
    'Pair Coeffs', 'Bond Coeffs', 'Angle Coeffs', 'Dihedral Coeffs', 'Improper Coeffs',
    'BondBond Coeffs', 'BondAngle Coeffs', 'MiddleBondTorsion Coeffs', 'EndBondTorsion Coeffs',
    'AngleTorsion Coeffs', 'AngleAngleTorsion Coeffs', 'BondBond13 Coeffs', 'AngleAngle Coeffs',
}
NA = 0.6022141  # amu/A^3 -> g/cm^3 conversion constant (Avogadro * 1e-24)


def density_from_log(path, tail_fraction=0.5):
    """Plateau-mean density (g/cm^3) from an NPT stage log's Density column.

    Preferred over density_from_data: an NPT box fluctuates by ~0.2-1% frame to frame, so the
    single final frame in the restart .data file is one draw from that distribution, not the
    stage's density. Both ends of the contraction ratio carry that error independently, and the
    melt-vs-cool split routes remedies on a few-percent gap. Averages the last tail_fraction of
    the log. Returns (None, None) if unavailable.
    """
    if not path or not os.path.exists(path):
        return None, None
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from analysis_utils import parse_lammps_log
        df = parse_lammps_log(path)
        if df is None or 'Density' not in df or len(df) < 4:
            return None, None
        vals = df['Density'].values[int(len(df) * (1.0 - tail_fraction)):]
        if len(vals) == 0:
            return None, None
        return float(vals.mean()), float(vals.std())
    except Exception:
        return None, None


def density_from_data(path):
    """Mass density (g/cm^3) from a LAMMPS data file: sum(type masses) / box volume.

    Reads the authoritative final structure (box + per-type atom counts + masses), so it is
    independent of whatever the thermo log happened to print. Handles orthogonal and triclinic
    boxes. Returns None if the file is missing or unparseable.
    """
    if not path or not os.path.exists(path):
        return None
    mass, counts, box = {}, {}, {}
    tilt = {'xy': 0.0, 'xz': 0.0, 'yz': 0.0}
    sec = None
    for ln in open(path, errors='ignore'):
        s = ln.strip()
        if not s:
            continue
        head = s.split('#')[0].strip()
        if head in SECTIONS:
            sec = head
            continue
        if 'xlo xhi' in ln:
            p = ln.split(); box['x'] = float(p[1]) - float(p[0]); continue
        if 'ylo yhi' in ln:
            p = ln.split(); box['y'] = float(p[1]) - float(p[0]); continue
        if 'zlo zhi' in ln:
            p = ln.split(); box['z'] = float(p[1]) - float(p[0]); continue
        if 'xy xz yz' in ln:
            p = ln.split(); tilt['xy'], tilt['xz'], tilt['yz'] = float(p[0]), float(p[1]), float(p[2]); continue
        if sec == 'Masses' and s.split()[0].isdigit():
            p = s.split(); mass[int(p[0])] = float(p[1])
        elif sec == 'Atoms' and s.split()[0].isdigit():
            t = int(s.split()[2]); counts[t] = counts.get(t, 0) + 1
    if not (box and mass and counts):
        return None
    # Orthogonal volume = lx*ly*lz; triclinic tilt does not change cell volume.
    V = box['x'] * box['y'] * box['z']
    M = sum(counts[t] * mass[t] for t in counts)
    return M / (NA * V)


def assess(rho_melt, rho_glass, tg_K, t_equil_K, alpha_glass=2.5e-4, alpha_melt=6e-4):
    """Self-consistency check: does the observed melt->glass contraction match the system's
    own thermal-expansion prediction? Pure function (testable). Never reads or needs an
    experimental/curated reference value -- see module docstring."""
    out = {'rho_melt': rho_melt, 'rho_glass': rho_glass, 'tg_K': tg_K, 't_equil_K': t_equil_K}
    if rho_glass is None:
        out['verdict'] = 'INSUFFICIENT_DATA'
        out['remedy'] = 'glass-state density (300 K) not found; cannot assess.'
        return out

    # Rubbery case: T_equil <= Tg means 300 K is at/above the production T (no glass).
    # There is no cooling stage to under-anneal; nothing self-referentially checkable.
    if t_equil_K is None or tg_K is None or tg_K <= 300.0:
        out['regime'] = 'rubbery_or_equilibrium'
        out['verdict'] = 'OK'
        out['remedy'] = 'no cooling stage to assess (rubbery/equilibrium regime).'
        out['under_annealed_cooling'] = False
        return out

    if not rho_melt:
        out['verdict'] = 'OK'
        out['remedy'] = 'melt-state density not available; nothing to diagnose without both endpoints.'
        out['under_annealed_cooling'] = False
        return out

    # Expected volumetric contraction V(T_equil)/V(300) along the system's own thermal path:
    # glassy segment (300 -> Tg) at alpha_glass, melt segment (Tg -> T_equil) at alpha_melt.
    expected_contraction = 1.0 + alpha_glass * (tg_K - 300.0) + alpha_melt * (t_equil_K - tg_K)
    actual_contraction = rho_glass / rho_melt
    shortfall = actual_contraction / expected_contraction  # <1 => under-contracted on cooling
    span = t_equil_K - 300.0
    reliable = span < 300.0  # alpha-extrapolation degrades over large cooling spans

    out['expected_contraction'] = round(expected_contraction, 4)
    out['actual_contraction'] = round(actual_contraction, 4)
    out['contraction_shortfall'] = round(shortfall, 4)
    out['extrapolation_reliable'] = reliable

    if shortfall < 0.97:
        out['verdict'] = 'UNDER_ANNEALED_COOLING'
        out['remedy'] = ('The cell gained too little density on cooling relative to its own '
                         'thermal-expansion prediction (free volume frozen in). REMEDY: re-melt '
                         '+ slow re-cool (reheat >Tg, re-equilibrate, cool at a lower rate / more '
                         'anneal cycles). Do NOT EXTEND at 300 K — a glass cannot densify below Tg.')
        out['under_annealed_cooling'] = True
    else:
        out['verdict'] = 'OK'
        out['remedy'] = 'cooling contraction is self-consistent with its own thermal-expansion prediction.'
        out['under_annealed_cooling'] = False

    if not reliable:
        out['remedy'] += (f' CAVEAT: cooling span {span:.0f} K is large; the alpha-based '
                          'expected contraction is unreliable here — treat this verdict as indicative.')
    return out


def make_markdown(a):
    lines = ['### Cooling-contraction self-consistency check', '']
    if a.get('rho_melt') is not None:
        lines.append(f"- Melt ρ(T_equil)={a['rho_melt']:.4f}, glass ρ(300K)={a.get('rho_glass'):.4f}")
    if 'actual_contraction' in a:
        lines.append(f"- Cooling contraction: actual ×{a['actual_contraction']:.3f} vs "
                     f"expected ×{a['expected_contraction']:.3f} "
                     f"(shortfall {a['contraction_shortfall']:.3f})")
    lines.append(f"- **Verdict: {a.get('verdict')}** — {a.get('remedy')}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--melt_data', help='npt_production_out.data at T_equil (melt). Optional but needed for the split.')
    ap.add_argument('--glass_data', required=True, help='npt_prod300_out.data at 300 K (glass).')
    ap.add_argument('--rho_melt', type=float, help='Override: melt density g/cm^3 (skip --melt_data parse).')
    ap.add_argument('--rho_glass', type=float, help='Override: glass density g/cm^3 (skip --glass_data parse).')
    ap.add_argument('--melt_log', help='npt_production.log — plateau-averaged melt density. '
                                       'Preferred over --melt_data (single fluctuating frame).')
    ap.add_argument('--glass_log', help='npt_prod300.log — plateau-averaged glass density. '
                                        'Preferred over --glass_data (single fluctuating frame).')
    ap.add_argument('--tg_K', type=float, required=True)
    ap.add_argument('--t_equil_K', type=float, required=True)
    ap.add_argument('--alpha_glass', type=float, default=2.5e-4)
    ap.add_argument('--alpha_melt', type=float, default=6e-4)
    args = ap.parse_args()

    # Precedence: explicit override > plateau mean from the stage log > single final frame.
    provenance = {}

    def _resolve(override, log_path, data_path, label):
        if override is not None:
            provenance[label] = 'override'
            return override, None
        mean, sd = density_from_log(log_path)
        if mean is not None:
            provenance[label] = f'plateau_mean({os.path.basename(log_path)})'
            return mean, sd
        provenance[label] = ('final_frame(%s)' % os.path.basename(data_path)) if data_path else 'unavailable'
        return density_from_data(data_path), None

    rho_melt, melt_sd = _resolve(args.rho_melt, args.melt_log, args.melt_data, 'rho_melt')
    rho_glass, glass_sd = _resolve(args.rho_glass, args.glass_log, args.glass_data, 'rho_glass')

    res = assess(rho_melt, rho_glass, args.tg_K, args.t_equil_K, args.alpha_glass, args.alpha_melt)
    res['density_provenance'] = provenance
    res['rho_melt_sd'] = melt_sd
    res['rho_glass_sd'] = glass_sd
    res['markdown'] = make_markdown(res)
    print(json.dumps(res, indent=2))


if __name__ == '__main__':
    main()
