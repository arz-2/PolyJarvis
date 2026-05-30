"""
patch_fluorine_params.py
------------------------
Post-processes a GAFF2/GAFF2_mod LAMMPS .data file to replace the Lennard-Jones
parameters for fluorine atom types with improved values that correct GAFF2's
known underestimation of F-F repulsion in CF2/CF3 backbones (PTFE, PVDF, PCTFE).

Usage:
    python patch_fluorine_params.py input.data output.data [--dry-run]

References (verify before filling IMPROVED_PARAMS below):
    [1] Damm, W. et al. J. Comput. Chem. 1997, 18, 1955-1970
        OPLS-AA/L organofluorine — the most likely source for improved F params;
        already cited in polymer_rules.json for PHAL class.
    [2] Byutner, O. & Smith, G.D. Macromolecules 2000, 33, 4264-4270
        QM-derived force field for PVDF — CF2 backbone specific.
    [3] Kamath, G. & Potoff, J.J. Fluid Phase Equilib. 2006, 246, 218-228
        TraPPE-UA for perfluorocarbons / PTFE-like backbones.

    NOTE: The original "Hait et al. JCTC 2020" citation in polymer_rules.json
    could not be verified. Use the sources above instead.

LAMMPS data file context:
    Pair style: lj/charmm/coul/long 8.0 12.0  (PPPM path, PHAL class)
    Coefficients written as: epsilon (kcal/mol)  sigma (Angstrom)
    Mixing rule: arithmetic (pair_modify mix arithmetic)
"""

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Fluorine LJ parameter sets
# ---------------------------------------------------------------------------

# GAFF2_mod defaults — what RadonPy actually writes into the .data file.
# (GAFF2_mod has different F params from bare GAFF2: ε=0.0832, σ=3.034 Å)
GAFF2_DEFAULTS = {
    "f":  {"epsilon": 0.0832, "sigma": 3.0342},  # aliphatic fluorine (GAFF2_mod)
    "fb": {"epsilon": 0.0832, "sigma": 3.0342},  # fluorine in aromatic rings (if present)
}

# ---------------------------------------------------------------------------
# Source: Watkins & Jorgensen, J. Phys. Chem. A 2001, 105, 4118-4125
# OPLS-AA for perfluoroalkanes (opls_965 F atom type)
#   sigma = 0.295 nm = 2.95 Å  (vs GAFF2 3.118 Å — smaller repulsive radius)
#   epsilon = 0.221752 kJ/mol / 4.184 = 0.0530 kcal/mol
#
# LJ-ONLY NOTE: Watkins & Jorgensen also developed new torsional parameters
# for CF2 chains (CCCC dihedral). This patch corrects nonbonded packing but
# a full fix for conformational behaviour requires torsional reparameterization.
# Track A scope is LJ-only; torsional patch is a separate follow-up task.
#
# "fb" (aromatic F) does not appear in PHAL polymers (PVDF/PTFE/PCTFE/PVF
# are all aliphatic), but kept in sync to avoid surprises if the type appears.
# ---------------------------------------------------------------------------
IMPROVED_PARAMS_OVERRIDE = {
    "f":  {"epsilon": 0.0530, "sigma": 2.9500},
    "fb": {"epsilon": 0.0530, "sigma": 2.9500},
}

# Active parameter set
IMPROVED_PARAMS = IMPROVED_PARAMS_OVERRIDE if IMPROVED_PARAMS_OVERRIDE is not None else GAFF2_DEFAULTS

# Atom type names to patch (comment field in Pair Coeffs section)
FLUORINE_TYPES = set(IMPROVED_PARAMS.keys())


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_data_file(path: Path) -> list[str]:
    with open(path) as f:
        return f.readlines()


def patch_pair_coeffs(lines: list[str], dry_run: bool = False) -> tuple[list[str], dict]:
    """
    Scan for the Pair Coeffs section and replace epsilon/sigma for fluorine types.
    Returns (patched_lines, report) where report maps atom_type -> old/new values.
    """
    in_section = False
    seen_data = False   # True once we've parsed at least one coeff line
    # matches: "   <int>   <float>   <float>   # <word>"
    coeff_re = re.compile(
        r'^(\s*\d+\s+)([0-9Ee.+-]+)(\s+)([0-9Ee.+-]+)(\s+#\s*)(\S+)(.*)'
    )
    patched = []
    report = {}

    for line in lines:
        stripped = line.strip()

        if re.match(r'^Pair\s+Coeffs', stripped):
            in_section = True
            seen_data = False
            patched.append(line)
            continue

        # Blank line ends the section only after we've seen at least one data line
        # (LAMMPS format has a blank line between header and first coeff)
        if in_section and stripped == '' and seen_data:
            in_section = False

        if in_section and stripped and not stripped.startswith('#'):
            seen_data = True
            m = coeff_re.match(line)
            if m:
                prefix, eps_old, gap, sig_old, hash_part, atype, tail = m.groups()
                # RadonPy appends a charge index: "f,0" → strip to get "f"
                atype_base = atype.split(',')[0]
                if atype_base in FLUORINE_TYPES:
                    atype = atype_base
                    new_eps = IMPROVED_PARAMS[atype]["epsilon"]
                    new_sig = IMPROVED_PARAMS[atype]["sigma"]
                    report[atype] = {
                        "old": (float(eps_old), float(sig_old)),
                        "new": (new_eps, new_sig),
                        "changed": (float(eps_old) != new_eps or float(sig_old) != new_sig),
                    }
                    if not dry_run:
                        line = f"{prefix}{new_eps:<12.7f}{gap}{new_sig:<12.7f}{hash_part}{atype}{tail}\n"

        patched.append(line)

    return patched, report


def main():
    parser = argparse.ArgumentParser(description="Patch fluorine LJ params in a GAFF2 LAMMPS .data file")
    parser.add_argument("input",  type=Path, help="Input LAMMPS .data file")
    parser.add_argument("output", type=Path, help="Output (patched) LAMMPS .data file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without writing output")
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"ERROR: input file not found: {args.input}")

    lines = parse_data_file(args.input)
    patched, report = patch_pair_coeffs(lines, dry_run=args.dry_run)

    if not report:
        print("INFO: No fluorine atom types found in Pair Coeffs — file unchanged.")
        if not args.dry_run:
            args.output.write_text("".join(patched))
        return

    for atype, info in report.items():
        status = "CHANGED" if info["changed"] else "unchanged"
        print(f"  {atype:6s}: eps {info['old'][0]:.7f} → {info['new'][0]:.7f}  "
              f"sig {info['old'][1]:.7f} → {info['new'][1]:.7f}  [{status}]")

    if args.dry_run:
        print("Dry run — no file written.")
    else:
        args.output.write_text("".join(patched))
        print(f"Patched file written to: {args.output}")


if __name__ == "__main__":
    main()
