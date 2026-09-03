#!/usr/bin/env python3
"""
extract_solubility_parameter.py — Cohesive energy density (CED) / Hildebrand
solubility parameter (delta) via a vacuum single-chain intramolecular-energy
reference, subtracted from a bulk NPT hold's total nonbonded energy.

Method (vacuum single-chain reference):
    LAMMPS's E_vdwl+E_coul(+E_long) in a bulk melt log is TOTAL nonbonded
    energy -- intramolecular (a chain folded back on itself) plus
    intermolecular (chain-to-chain, the part that actually resists tension).
    These are NOT separable from the bulk log alone; for a real coiled melt
    the intramolecular share is not a rounding error, so using the raw total
    as a cohesion proxy would misclassify cohesion, not just add noise.

    This script isolates the intramolecular part with a SEPARATE short NVT
    hold of one isolated chain of the same topology/force field, at low
    density (large box, no periodic-image contacts) -- in that run, ALL
    nonbonded energy is intramolecular by construction:

        E_inter_total = E_bulk_total - n_chains * E_intra_per_chain
        CED           = -E_inter_total / V_bulk        (J/cm^3 == MPa)
        delta         = sqrt(CED)                       (MPa^0.5)

    This is an approximation relative to a true per-molecule decomposition
    (RadonPy's SPMD_analyze.Solubility_Parameter does that properly, via a
    LAMMPS rerun with pe/mol/tally computes -- see the sibling, currently
    inactive, extract_solubility_parameter_tally.py, gated on a TALLY-enabled
    LAMMPS binary that doesn't exist yet). This script uses one averaged
    single-chain reference rather than a per-molecule tally.

    CAUTION: measure per SPECIFIC SYSTEM, never cache/reuse across a nominal
    polymer class -- different monomers in the same class (e.g. PLA/PET/PCL
    in PEST) can have meaningfully different cohesion.

Usage:
    python extract_solubility_parameter.py \\
        --bulk_log /path/to/cool/npt_final/npt_final.log \\
        --vacuum_log /path/to/nvt_vacuum_chain.log \\
        --n_chains 20 \\
        --output_dir /path/to/raw/ \\
        [--charge_method none] [--eq_fraction 0.5] [--system_label PE4]

References:
    docs/ROADMAP.md Track J2 (physical quantity/units); corrected this session
    to use a vacuum single-chain reference instead of the raw uncorrected
    E_pair/V post-process, which double-counts intramolecular energy.
"""

import argparse
import json
from pathlib import Path

from analysis_utils import parse_lammps_log

KCAL_PER_MOL_TO_J = 4184.0 / 6.02214076e23  # per simulated cell, not per literal mole
A3_TO_CM3 = 1e-24


def _nonbonded_energy_columns(df):
    vdwl = next((c for c in ["E_vdwl", "Evdwl", "evdwl"] if c in df.columns), None)
    coul = next((c for c in ["E_coul", "Ecoul", "ecoul"] if c in df.columns), None)
    longc = next((c for c in ["E_long", "Elong", "elong"] if c in df.columns), None)
    if vdwl is None or coul is None:
        raise ValueError(
            f"Missing E_vdwl/E_coul thermo columns. Available: {list(df.columns)}. "
            "thermo_style must include 'evdwl ecoul' (already standard in every "
            "PolyJarvis production template)."
        )
    return vdwl, coul, longc


def tail_mean_nonbonded_energy(log_path, eq_fraction):
    """Tail-window mean/std of total nonbonded energy (kcal/mol) and mean Volume (A^3),
    using the same production-window convention as extract_bulk_modulus_murnaghan.py."""
    df = parse_lammps_log(log_path)
    vdwl, coul, longc = _nonbonded_energy_columns(df)
    n = len(df)
    n_discard = int(n * (1.0 - eq_fraction))
    prod = df.iloc[n_discard:]
    if len(prod) < 10:
        raise ValueError(
            f"Only {len(prod)} production rows in {log_path} after discarding "
            f"{n_discard} burn-in rows (eq_fraction={eq_fraction})."
        )
    e_nb = prod[vdwl] + prod[coul]
    if longc is not None:
        e_nb = e_nb + prod[longc]
    vol_col = next((c for c in ["Volume", "Vol", "vol"] if c in prod.columns), None)
    mean_vol_A3 = float(prod[vol_col].mean()) if vol_col is not None else None
    return float(e_nb.mean()), float(e_nb.std()), mean_vol_A3, len(prod)


def compute_solubility_parameter(bulk_log, vacuum_log, n_chains, eq_fraction=0.5,
                                  charge_method=None, system_label=None):
    e_bulk_total, e_bulk_std, v_bulk_A3, n_bulk_rows = tail_mean_nonbonded_energy(
        bulk_log, eq_fraction)
    e_intra_per_chain, e_intra_std, v_vac_A3, n_vac_rows = tail_mean_nonbonded_energy(
        vacuum_log, eq_fraction)

    if v_bulk_A3 is None:
        raise ValueError(f"No volume column in {bulk_log}")
    if n_chains < 1:
        raise ValueError(f"n_chains must be >= 1, got {n_chains}")

    e_inter_total_kcal_mol = e_bulk_total - n_chains * e_intra_per_chain
    # -E_inter is the cohesive (separation) energy; positive for a condensed phase.
    e_cohesive_J = -e_inter_total_kcal_mol * KCAL_PER_MOL_TO_J
    v_bulk_cm3 = v_bulk_A3 * A3_TO_CM3
    ced_J_cm3 = e_cohesive_J / v_bulk_cm3  # numerically == MPa (1 J/cm^3 == 1 MPa)

    warnings = []
    if ced_J_cm3 < 0:
        warnings.append(
            "Computed CED is negative (bulk shows LESS net attraction than "
            "n_chains isolated copies would) -- check that the vacuum cell "
            "used the same force field/charges as the bulk hold, and that "
            "both logs' production windows are genuinely equilibrated."
        )
        delta_MPa0p5 = None
    else:
        delta_MPa0p5 = ced_J_cm3 ** 0.5

    cm = (charge_method or "").strip().lower()
    ced_confidence = "degraded" if cm in ("", "none", "gasteiger") else "high"
    if ced_confidence == "degraded":
        warnings.append(
            f"charge_method={charge_method!r} -- docs/ROADMAP.md flags 20%+ CED "
            "error risk for embedded/Gasteiger-charged (typically TraPPE-UA) "
            "systems; treat the absolute delta as approximate, though it may "
            "still be reliable enough for classification if it isn't near a "
            "decision threshold."
        )

    return {
        "system_label": system_label,
        "method": "vacuum_single_chain_reference",
        "CED_J_per_cm3": ced_J_cm3,
        "CED_MPa": ced_J_cm3,
        "solubility_parameter_MPa0p5": delta_MPa0p5,
        "ced_confidence": ced_confidence,
        "charge_method": charge_method,
        "n_chains": n_chains,
        "e_bulk_total_nonbonded_kcal_mol": e_bulk_total,
        "e_bulk_total_nonbonded_std_kcal_mol": e_bulk_std,
        "e_intra_per_chain_kcal_mol": e_intra_per_chain,
        "e_intra_per_chain_std_kcal_mol": e_intra_std,
        "e_inter_total_kcal_mol": e_inter_total_kcal_mol,
        "v_bulk_A3": v_bulk_A3,
        "v_vacuum_chain_A3": v_vac_A3,
        "n_bulk_prod_rows": n_bulk_rows,
        "n_vacuum_prod_rows": n_vac_rows,
        "eq_fraction": eq_fraction,
        "bulk_log": str(bulk_log),
        "vacuum_log": str(vacuum_log),
        "warnings": warnings,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--bulk_log", required=True,
                   help="Bulk NPT hold log (npt_final.log, or npt_melt_hold.log for a melt).")
    p.add_argument("--vacuum_log", required=True,
                   help="Single-chain, low-density NVT hold log (same FF/T).")
    p.add_argument("--n_chains", type=int, required=True,
                   help="Number of chains in the bulk cell (a known build parameter).")
    p.add_argument("--output_dir", required=True)
    p.add_argument("--charge_method", default=None,
                   help="e.g. none/Gasteiger/AM1-BCC/RESP -- sets ced_confidence.")
    p.add_argument("--eq_fraction", type=float, default=0.5)
    p.add_argument("--system_label", default=None,
                   help="e.g. PE4 -- for traceability only, never a class name.")
    args = p.parse_args()

    result = compute_solubility_parameter(
        bulk_log=args.bulk_log,
        vacuum_log=args.vacuum_log,
        n_chains=args.n_chains,
        eq_fraction=args.eq_fraction,
        charge_method=args.charge_method,
        system_label=args.system_label,
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "solubility_parameter.json"
    out_path.write_text(json.dumps(result, indent=2))
    result["output_json"] = str(out_path)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
