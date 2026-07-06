#!/usr/bin/env python3
"""
assess_cooling_contraction.py — melt-vs-glass density decomposition for the equil gate.

A converged 300 K density tells you the cell stopped moving — NOT that it stopped at the
right value. A kinetically trapped (under-annealed) glass converges at a too-low density
because free volume is frozen in during cooling. This script separates the two failure
modes the convergence checks cannot:

    glass-density deficit  =  melt-stage deficit  +  cooling-stage deficit

  - melt-stage deficit  : the equilibrated MELT density (at T_equil, chains mobile) is
                          already low vs experiment-extrapolated melt. Mechanism is force-field
                          underbinding OR melt-stage under-annealing (NkepsuMbitou-style 10-TAC
                          melt annealing fixes the latter). NOT fixed by re-cooling.
  - cooling-stage deficit: the melt is fine but the glass gained less density on cooling than
                          the system's own thermal expansion predicts -> free volume frozen in
                          = under-annealed at the COOLING stage. Fixed by slower re-cool /
                          longer sub-Tg anneal (re-melt + slow re-cool), NOT by NPT-at-300K EXTEND.

The verdict ROUTES THE REMEDY; the hard pass/fail stays on the absolute glass-vs-experiment
density (caller's job). The alpha-based expected contraction is only a routing heuristic and
is flagged unreliable for large cooling spans (e.g. PEEK, 474 K).

Usage:
    python assess_cooling_contraction.py \
        --melt_data  /path/npt_production_out.data \
        --glass_data /path/npt_prod300_out.data \
        --exp_density_gcm3 1.19 --tg_K 378 --t_equil_K 550 \
        [--alpha_glass 2.5e-4] [--alpha_melt 6e-4] \
        [--band_pct 5.0]

Emits JSON to stdout: rho_melt, rho_glass, expected_contraction, actual_contraction,
contraction_shortfall, melt_density_gap_pct, glass_density_gap_pct, under_annealed_cooling,
verdict, remedy, extrapolation_reliable, markdown.
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


def assess(rho_melt, rho_glass, exp_density, tg_K, t_equil_K,
           alpha_glass=2.5e-4, alpha_melt=6e-4, band_pct=5.0):
    """Decompose the glass-density deficit and route a remedy. Pure function (testable)."""
    out = {
        'rho_melt': rho_melt, 'rho_glass': rho_glass, 'exp_density_gcm3': exp_density,
        'tg_K': tg_K, 't_equil_K': t_equil_K,
    }
    if rho_glass is None:
        out['verdict'] = 'INSUFFICIENT_DATA'
        out['remedy'] = 'glass-state density (300 K) not found; cannot assess.'
        return out

    glass_gap = (rho_glass / exp_density - 1.0) * 100.0
    out['glass_density_gap_pct'] = round(glass_gap, 2)

    # Rubbery case: T_equil <= Tg means 300 K is at/above the production T (no glass).
    # There is no cooling stage to under-anneal; the 300 K density is an equilibrium property.
    if t_equil_K is None or tg_K is None or tg_K <= 300.0:
        out['regime'] = 'rubbery_or_equilibrium'
        out['verdict'] = 'OK' if glass_gap >= -band_pct else 'MELT_STAGE_DEFICIT'
        out['remedy'] = ('within band' if glass_gap >= -band_pct else
                         'equilibrium density low: force-field underbinding OR melt-stage '
                         'under-annealing. No cooling stage. Probe with a heavy melt anneal '
                         '(NkepsuMbitou 10-TAC); if it plateaus low, it is FF.')
        out['under_annealed_cooling'] = False
        return out

    # Expected volumetric contraction V(T_equil)/V(300) along the system's own thermal path:
    # glassy segment (300 -> Tg) at alpha_glass, melt segment (Tg -> T_equil) at alpha_melt.
    expected_contraction = 1.0 + alpha_glass * (tg_K - 300.0) + alpha_melt * (t_equil_K - tg_K)
    exp_melt = exp_density / expected_contraction
    span = t_equil_K - 300.0
    reliable = span < 300.0  # alpha-extrapolation degrades over large cooling spans

    out['expected_contraction'] = round(expected_contraction, 4)
    out['exp_extrapolated_melt_gcm3'] = round(exp_melt, 4)
    out['extrapolation_reliable'] = reliable

    if rho_melt:
        melt_gap = (rho_melt / exp_melt - 1.0) * 100.0
        actual_contraction = rho_glass / rho_melt
        shortfall = actual_contraction / expected_contraction  # <1 => under-contracted on cooling
        out['melt_density_gap_pct'] = round(melt_gap, 2)
        out['actual_contraction'] = round(actual_contraction, 4)
        out['contraction_shortfall'] = round(shortfall, 4)
    else:
        melt_gap = None
        shortfall = None
        out['melt_density_gap_pct'] = None

    # --- verdict / remedy routing ---
    if glass_gap >= -band_pct:
        out['verdict'] = 'OK'
        out['remedy'] = 'glass density within band; no action.'
        out['under_annealed_cooling'] = False
    elif melt_gap is not None and melt_gap > -1.5 and shortfall is not None and shortfall < 0.97:
        # melt density is right, but the cell under-contracted on cooling -> trapped free volume
        out['verdict'] = 'UNDER_ANNEALED_COOLING'
        out['remedy'] = ('Melt density matches experiment but the cell gained too little density '
                         'on cooling (free volume frozen in). REMEDY: re-melt + slow re-cool '
                         '(reheat >Tg, re-equilibrate, cool at a lower rate / more anneal cycles). '
                         'Do NOT EXTEND at 300 K — a glass cannot densify below Tg.')
        out['under_annealed_cooling'] = True
    elif melt_gap is not None and melt_gap <= -1.5:
        out['verdict'] = 'MELT_STAGE_DEFICIT'
        out['remedy'] = ('Deficit is in the equilibrated melt (low melt density), not the cooling '
                         'stage. Mechanism is force-field underbinding OR melt-stage under-annealing '
                         '— not separable here. Probe with a heavy melt anneal (NkepsuMbitou 10-TAC '
                         'from low density); if melt density plateaus low it is FF, else it was '
                         'under-annealed. Re-cooling will NOT fix it.')
        out['under_annealed_cooling'] = False
    else:
        out['verdict'] = 'AMBIGUOUS'
        out['remedy'] = ('Glass density below band but melt/cooling split is inconclusive '
                         '(missing melt density or borderline). Recover via re-melt + slow re-cool '
                         'first; if unchanged, treat as melt-stage/FF.')
        out['under_annealed_cooling'] = False

    if not reliable:
        out['remedy'] += (f' CAVEAT: cooling span {span:.0f} K is large; the alpha-based '
                          'expected contraction is unreliable here — treat the melt/cooling split '
                          'as indicative, and lean on the absolute glass-vs-exp density as the gate.')
    return out


def make_markdown(a):
    g = a.get('glass_density_gap_pct')
    lines = ['### Cooling-contraction decomposition (under-anneal check)',
             '',
             f"- Glass ρ(300 K) gap vs exp: **{g:+.1f}%**" if g is not None else "- Glass ρ: n/a",
             ]
    if a.get('rho_melt') is not None:
        lines.append(f"- Melt ρ(T_equil)={a['rho_melt']:.4f}, glass ρ(300K)={a['rho_glass']:.4f}")
    if 'melt_density_gap_pct' in a and a['melt_density_gap_pct'] is not None:
        lines.append(f"- Melt-density gap vs exp-extrapolated melt: {a['melt_density_gap_pct']:+.1f}%")
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
    ap.add_argument('--exp_density_gcm3', type=float, required=True)
    ap.add_argument('--tg_K', type=float, required=True)
    ap.add_argument('--t_equil_K', type=float, required=True)
    ap.add_argument('--alpha_glass', type=float, default=2.5e-4)
    ap.add_argument('--alpha_melt', type=float, default=6e-4)
    ap.add_argument('--band_pct', type=float, default=5.0)
    args = ap.parse_args()

    rho_melt = args.rho_melt if args.rho_melt is not None else density_from_data(args.melt_data)
    rho_glass = args.rho_glass if args.rho_glass is not None else density_from_data(args.glass_data)

    res = assess(rho_melt, rho_glass, args.exp_density_gcm3, args.tg_K, args.t_equil_K,
                 args.alpha_glass, args.alpha_melt, args.band_pct)
    res['markdown'] = make_markdown(res)
    print(json.dumps(res, indent=2))


if __name__ == '__main__':
    main()
