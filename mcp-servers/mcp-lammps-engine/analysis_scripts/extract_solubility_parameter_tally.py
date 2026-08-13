#!/usr/bin/env python3
"""
extract_solubility_parameter_tally.py — Cohesive energy density (CED) /
Hildebrand solubility parameter (delta) via a true per-molecule energy
decomposition, re-implementing the physics of RadonPy's
`radonpy.sim.preset.sp.SPMD.rerun()` / `SPMD_analyze.Solubility_Parameter()`
(/home/arz2/RadonPy/radonpy/sim/preset/sp.py) in this project's own plain
functional style (stdlib+numpy+pandas, matching every other script in
analysis_scripts/) rather than RadonPy's Preset/MD OOP framework, which this
project doesn't use elsewhere.

*** INACTIVE — DO NOT WIRE INTO ANY WORKFLOW YET ***
This script is gated on a precondition that does not exist as of this writing:
LAMMPS's TALLY package (compute_pe_mol_tally.cpp, compute_force_tally.cpp, ...)
must be compiled into the LAMMPS binary that runs the rerun below. Neither of
this project's two production binaries (lammps-install, lammps-install-kokkos)
has PKG_TALLY enabled (`grep PKG_TALLY .../CMakeCache.txt` -> OFF in both). The
LAMMPS *source* tree at /home/arz2/lammps already contains the TALLY package —
building a third, separate binary with PKG_TALLY=yes is confirmed low-risk (it
never touches the two binaries every live run depends on) but is its own,
not-yet-done, ops step (docs/ROADMAP.md Track J2b). Until that binary exists
and a real rerun log has been produced with it, this script has no valid input
to run against — it is here so the physics/parsing logic is ready to activate,
not because it has been used yet.

Compare: mcp-lammps-engine/analysis_scripts/extract_solubility_parameter.py is
the ACTIVE, already-usable method for the same physical quantity, via a
separate vacuum single-chain reference simulation instead of a rerun. It is a
coarser approximation (one averaged intramolecular reference for every chain,
vs. this script's true per-molecule tally) but needs no new LAMMPS package.

Method (verified against RadonPy's own formula, dimensionally identical to
extract_solubility_parameter.py's vacuum-single-chain approach — both reduce
to CED = -E_inter_total / V_bulk; RadonPy gets its intramolecular reference
per-molecule from a rerun of the bulk trajectory itself, rather than from a
separate simulation):

    For each of the n_chains molecules in the cell, add during a LAMMPS
    `rerun` of the bulk trajectory dump:
        group mol{i} molecule {i+1}
        compute mol{i}_kspace mol{i} group/group mol{i} pair no kspace yes molecule intra
        variable mol{i}_elong_intra equal -c_mol{i}_kspace
        compute mol{i}_pair mol{i} pe/mol/tally mol{i}
        variable mol{i}_evdw_intra  equal -c_mol{i}_pair[1]
        variable mol{i}_ecoul_intra equal -c_mol{i}_pair[2]
    (each variable added to thermo_style so it's printed every rerun step)

    Then, from the rerun log's thermo table:
        etotal_intra_per_chain = mean_over_chains(evdw_intra + ecoul_intra + elong_intra)  [J/mol]
        etotal_inter_per_chain = (E_vdwl + E_coul + E_long) / n_chains                     [J/mol]
        CED   = (etotal_intra_per_chain - etotal_inter_per_chain) / Vm   [J/cm^3 == MPa]
        delta = sqrt(CED)                                                 [MPa^0.5]
    where Vm = V_bulk * N_A / n_chains (molar volume per mole of chains).

    This is the SAME physical quantity as extract_solubility_parameter.py's
    CED = -(E_bulk_total - n_chains*E_intra_per_chain)/V_bulk (both reduce to
    -intermolecular_energy_total/V_bulk); the difference is only in how the
    intramolecular reference is obtained (true per-molecule tally within the
    bulk trajectory itself here, vs. one separate vacuum-chain simulation
    there).

Usage (once the TALLY-enabled binary exists):
    # 1. Generate the rerun .in fragment to append after `read_data`/the base
    #    force-field block, before `run` -- the rerun command itself is
    #    appended by add_rerun_block() (a real trajectory dump replaces
    #    ordinary dynamics).
    python extract_solubility_parameter_tally.py generate-rerun-block \\
        --n_chains 20 --dump_file eq.dump > rerun_block.in

    # 2. After running that rerun .in through the TALLY-enabled LAMMPS binary
    #    (producing a log with the added v_mol{i}_* thermo columns):
    python extract_solubility_parameter_tally.py analyze \\
        --rerun_log /path/to/rerun.log --n_chains 20 \\
        --output_dir /path/to/raw/ [--charge_method AM1-BCC] [--system_label PE4]

References:
    /home/arz2/RadonPy/radonpy/sim/preset/sp.py (SPMD.rerun, SPMD_analyze.Solubility_Parameter)
    docs/ROADMAP.md Track J2 / J2b
"""

import argparse
import json
from pathlib import Path

import numpy as np

from analysis_utils import parse_lammps_log

CAL_TO_J = 4.184          # matches radonpy.core.const.cal2j exactly
NA = 6.02214076e23        # Avogadro's number, matches radonpy.core.const.NA
A3_TO_CM3 = 1e-24


def generate_rerun_block(n_chains):
    """Return the LAMMPS input fragment (list of lines) that must be inserted
    into a rerun .in script, after the force-field/read_data block and before
    the `rerun` command, to compute a true per-molecule intramolecular energy
    decomposition. One-to-one port of SPMD.rerun()'s per-chain compute/variable
    block (sp.py lines 71-78) -- LAMMPS molecule IDs are 1-indexed, this
    function's chain index i is 0-indexed to match RadonPy's own convention.

    Caution (carried over verbatim from RadonPy's own docstring, sp.py:114):
    "the number of molecules must always be less than 31" -- this project's
    real nchain values (6-20, per guides/polymer_rules.json) are always under
    that ceiling, but a caller building a larger custom cell should split the
    rerun or investigate before assuming this scales further.
    """
    if n_chains < 1:
        raise ValueError(f"n_chains must be >= 1, got {n_chains}")
    if n_chains >= 31:
        raise ValueError(
            f"n_chains={n_chains} >= 31 -- RadonPy's own SPMD_analyze docstring "
            "caveats that molecule count must stay under 31 for this method; "
            "investigate before using it at this scale."
        )
    lines = []
    thermo_extra = []
    for i in range(n_chains):
        mol_id = i + 1  # LAMMPS molecule IDs are 1-indexed
        lines.append(f"group mol{i} molecule {mol_id}")
        lines.append(f"compute mol{i}_kspace mol{i} group/group mol{i} pair no kspace yes molecule intra")
        lines.append(f"variable mol{i}_elong_intra equal -c_mol{i}_kspace")
        lines.append(f"compute mol{i}_pair mol{i} pe/mol/tally mol{i}")
        lines.append(f"variable mol{i}_evdw_intra equal -c_mol{i}_pair[1]")
        lines.append(f"variable mol{i}_ecoul_intra equal -c_mol{i}_pair[2]")
        thermo_extra += [f"v_mol{i}_evdw_intra", f"v_mol{i}_ecoul_intra", f"v_mol{i}_elong_intra"]
    lines.append("# Append the following to your existing thermo_style custom line:")
    lines.append("# " + " ".join(thermo_extra))
    return lines


def add_rerun_block(dump_file, first_step=None, last_step=None):
    """The `rerun` command line itself (sp.py: add_rerun -> LAMMPS `rerun` cmd).
    Re-evaluates an EXISTING trajectory dump frame-by-frame with the computes
    added by generate_rerun_block(), instead of running new dynamics."""
    rng = ""
    if first_step is not None or last_step is not None:
        rng = f" first {first_step or 0} last {last_step or 1000000000}"
    return f"rerun {dump_file}{rng} dump x y z ix iy iz box yes"


def _thermo_energy_columns(df):
    vdwl = next((c for c in ["E_vdwl", "Evdwl", "evdwl"] if c in df.columns), None)
    coul = next((c for c in ["E_coul", "Ecoul", "ecoul"] if c in df.columns), None)
    longc = next((c for c in ["E_long", "Elong", "elong"] if c in df.columns), None)
    if vdwl is None or coul is None:
        raise ValueError(f"Missing E_vdwl/E_coul columns. Available: {list(df.columns)}")
    return vdwl, coul, longc


def analyze_rerun_log(rerun_log, n_chains, eq_fraction=0.5, charge_method=None,
                       system_label=None):
    """Port of SPMD_analyze.Solubility_Parameter(), reading a rerun log that
    already has the v_mol{i}_evdw_intra/ecoul_intra/elong_intra columns added
    by generate_rerun_block(). Tail-window mean over the production fraction,
    same convention as every other script in this directory."""
    df = parse_lammps_log(rerun_log)
    n = len(df)
    n_discard = int(n * (1.0 - eq_fraction))
    prod = df.iloc[n_discard:]
    if len(prod) < 10:
        raise ValueError(
            f"Only {len(prod)} production rows in {rerun_log} after discarding "
            f"{n_discard} burn-in rows (eq_fraction={eq_fraction})."
        )

    evdw_cols = [c for c in prod.columns if c.endswith("_evdw_intra")]
    ecoul_cols = [c for c in prod.columns if c.endswith("_ecoul_intra")]
    elong_cols = [c for c in prod.columns if c.endswith("_elong_intra")]
    if not evdw_cols or not ecoul_cols:
        raise ValueError(
            f"No v_mol{{i}}_evdw_intra/ecoul_intra columns found in {rerun_log} -- "
            "this log wasn't produced from a .in generated by generate_rerun_block(), "
            "or the TALLY package isn't active (see module docstring)."
        )
    if len(evdw_cols) != n_chains:
        raise ValueError(
            f"Found {len(evdw_cols)} per-chain intra columns but n_chains={n_chains} "
            "-- mismatch between the rerun .in actually used and this call's n_chains."
        )

    # RadonPy's variables are already negated once (`-c_..._pair[...]`); its own
    # analysis applies a second `*-1`, netting the raw (positive-convention)
    # compute value. Reproduced exactly (sp.py lines 122-128).
    evdw_intra = -1.0 * prod[evdw_cols].mean(axis=1) * CAL_TO_J * 1000.0     # kcal/mol -> J/mol, per chain
    ecoul_short_intra = -1.0 * prod[ecoul_cols].mean(axis=1) * CAL_TO_J * 1000.0
    ecoul_long_intra = (-1.0 * prod[elong_cols].mean(axis=1) * CAL_TO_J * 1000.0
                         if elong_cols else 0.0)
    etotal_intra_per_chain = float((evdw_intra + ecoul_short_intra + ecoul_long_intra).mean())

    vdwl, coul, longc = _thermo_energy_columns(prod)
    e_bulk_total_kcal_mol = prod[vdwl] + prod[coul] + (prod[longc] if longc else 0.0)
    etotal_inter_per_chain = float(e_bulk_total_kcal_mol.mean()) * CAL_TO_J * 1000.0 / n_chains  # J/mol per chain

    vol_col = next((c for c in ["Volume", "Vol", "vol"] if c in prod.columns), None)
    if vol_col is None:
        raise ValueError(f"No volume column in {rerun_log}")
    V_bulk_A3 = float(prod[vol_col].mean())
    Vm_cm3_per_mol = V_bulk_A3 * A3_TO_CM3 * NA / n_chains  # molar volume per mole of chains

    ced_J_cm3 = (etotal_intra_per_chain - etotal_inter_per_chain) / Vm_cm3_per_mol  # == MPa

    warnings = []
    if ced_J_cm3 < 0:
        warnings.append(
            "Computed CED is negative -- check the rerun .in actually matches "
            "generate_rerun_block()'s output and that the dump/production window "
            "is genuinely equilibrated."
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
            "systems, though this per-molecule tally method should be more "
            "robust to that than the vacuum single-chain approximation."
        )

    return {
        "system_label": system_label,
        "method": "radonpy_tally_rerun",
        "CED_J_per_cm3": ced_J_cm3,
        "CED_MPa": ced_J_cm3,
        "solubility_parameter_MPa0p5": delta_MPa0p5,
        "ced_confidence": ced_confidence,
        "charge_method": charge_method,
        "n_chains": n_chains,
        "etotal_intra_per_chain_J_mol": etotal_intra_per_chain,
        "etotal_inter_per_chain_J_mol": etotal_inter_per_chain,
        "v_bulk_A3": V_bulk_A3,
        "vm_cm3_per_mol": Vm_cm3_per_mol,
        "n_prod_rows": len(prod),
        "eq_fraction": eq_fraction,
        "rerun_log": str(rerun_log),
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gen = sub.add_parser("generate-rerun-block",
                            help="Print the LAMMPS .in fragment for a TALLY-based rerun.")
    p_gen.add_argument("--n_chains", type=int, required=True)
    p_gen.add_argument("--dump_file", required=True,
                        help="Trajectory dump to rerun (for the trailing `rerun` command).")
    p_gen.add_argument("--first_step", type=int, default=None)
    p_gen.add_argument("--last_step", type=int, default=None)

    p_an = sub.add_parser("analyze",
                           help="Parse a completed TALLY rerun log and compute CED/delta.")
    p_an.add_argument("--rerun_log", required=True)
    p_an.add_argument("--n_chains", type=int, required=True)
    p_an.add_argument("--output_dir", required=True)
    p_an.add_argument("--charge_method", default=None)
    p_an.add_argument("--eq_fraction", type=float, default=0.5)
    p_an.add_argument("--system_label", default=None)

    args = parser.parse_args()

    if args.cmd == "generate-rerun-block":
        lines = generate_rerun_block(args.n_chains)
        lines.append(add_rerun_block(args.dump_file, args.first_step, args.last_step))
        print("\n".join(lines))
        return

    result = analyze_rerun_log(
        rerun_log=args.rerun_log,
        n_chains=args.n_chains,
        eq_fraction=args.eq_fraction,
        charge_method=args.charge_method,
        system_label=args.system_label,
    )
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "solubility_parameter_tally.json"
    out_path.write_text(json.dumps(result, indent=2))
    result["output_json"] = str(out_path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
