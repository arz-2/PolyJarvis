"""
smiles_to_emc.py
----------------
Convert a repeat-unit SMILES (with * connection points) to an EMC/PCFF
amorphous cell build, producing a LAMMPS .data file ready for PolyJarvis
Stage 2 (equilibration).

The SMILES convention matches RadonPy: exactly two * atoms mark the left and
right chain-end connection points of the repeat unit.

Usage (CLI):
    python smiles_to_emc.py SMILES output_dir [options]

Usage (Python):
    from smiles_to_emc import build_cell
    data_path = build_cell(smiles, output_dir, dp=20, nchains=10, density=0.9)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# EMC installation
# ---------------------------------------------------------------------------

EMC_ROOT = Path(os.environ.get("EMC_ROOT", Path.home() / "emc"))
EMC_BIN = EMC_ROOT / "bin" / "emc_linux_x86_64"
EMC_SETUP = EMC_ROOT / "scripts" / "emc_setup.pl"


def _check_emc():
    if not EMC_BIN.exists():
        raise RuntimeError(
            f"EMC binary not found at {EMC_BIN}. "
            "Set EMC_ROOT or install EMC at ~/emc."
        )
    if not EMC_SETUP.exists():
        raise RuntimeError(f"emc_setup.pl not found at {EMC_SETUP}.")


# ---------------------------------------------------------------------------
# .esh generation
# ---------------------------------------------------------------------------

def make_esh(
    smiles: str,
    field: str = "pcff",
    density: float = 0.9,
    ntotal: int = 3000,
    dp: int = 20,
) -> str:
    """
    Generate EMC .esh file content from a repeat-unit SMILES.

    The SMILES must contain exactly two * atoms:
      - First * = left chain-end connection point
      - Second * = right chain-end connection point

    seed and temperature are passed as emc_setup.pl CLI flags (not .esh options).
    Returns the .esh file as a string (does not write to disk).
    """
    n_stars = smiles.count("*")
    if n_stars != 2:
        raise ValueError(
            f"SMILES must have exactly 2 * connection points, found {n_stars}: {smiles!r}"
        )

    # Connection spec for PCFF / OPLS-AA (all-atom fields):
    #   repeat group's left connection (1) bonds to the adjacent repeat's right connection (2)
    #   cap group's single connection (1) can terminate either end of the repeat unit
    #   cap chemistry: *[H] — explicit H atom type present in PCFF and OPLS-AA
    #
    # Connection spec for TraPPE-UA (united-atom field):
    #   Hydrogen is IMPLICIT in united-atom; *[H] has no UA atom type → EMC exits with
    #   "Missing rules." Use *C (CH3 methyl UA group) as chain-end cap instead.
    #   Connection spec goes on the repeat line: repeat knows it can bond to cap.
    #   Validated against EMC v9.4.4 trappe-ua.top rule 69: c4h3 = C(C) (one neighbour).
    is_trappe = "trappe" in field.lower()
    if is_trappe:
        repeat_connect = f"{smiles},1,repeat:2, 1,cap:1, 2,cap:1"
        cap_line = "*C"
    else:
        repeat_connect = f"{smiles},1,repeat:2"
        cap_line = "*[H],1,repeat:1,1,repeat:2"
    return f"""\
ITEM OPTIONS

replace         true
field           {field}
density         {density:.6f}
ntotal          {ntotal}

ITEM END

ITEM GROUPS

repeat   {repeat_connect}
cap      {cap_line}

ITEM END

ITEM CLUSTERS

poly    alternate    1

ITEM END

ITEM POLYMERS

poly
100    repeat,{dp},cap,2

ITEM END
"""


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def run_emc_setup(
    esh_path: Path,
    field: str = "pcff",
    seed: int = -1,
    temperature: float = 300.0,
) -> Path:
    """
    Run emc_setup.pl on the given .esh file.
    Post-processes build.emc to replace the ~emc placeholder with $root
    so the EMC binary can resolve the field file path at runtime.

    Returns the path to the generated build.emc.
    """
    env = {**os.environ, "EMC_ROOT": str(EMC_ROOT)}
    cmd = [
        "perl", str(EMC_SETUP),
        f"-field={field}",
        f"-seed={seed}",
        f"-temperature={temperature:.1f}",
        "-replace",
        str(esh_path.name),
    ]
    subprocess.run(
        cmd,
        cwd=esh_path.parent,
        env=env,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    build_emc = esh_path.parent / "build.emc"
    if not build_emc.exists():
        raise RuntimeError(f"emc_setup.pl did not produce build.emc in {esh_path.parent}")

    # emc_setup.pl writes "~emc/field/" as a placeholder that only resolves
    # when the binary is run from the emc root. Replace with the EMC script
    # variable $root so the binary resolves it correctly regardless of cwd.
    text = build_emc.read_text()
    text = text.replace('"~emc/field/"', '$root+"field/"')
    build_emc.write_text(text)

    return build_emc


def run_emc_build(build_emc: Path) -> Path:
    """
    Run the EMC binary on build.emc to generate the LAMMPS .data file.
    Returns the path to the generated .data file.
    """
    env = {**os.environ, "EMC_ROOT": str(EMC_ROOT)}
    result = subprocess.run(
        [str(EMC_BIN), str(build_emc.name)],
        cwd=build_emc.parent,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"EMC build failed (exit {result.returncode}):\n"
            f"{result.stdout}\n{result.stderr}"
        )

    # Find the .data file — EMC names it after the 'output' variable in build.emc
    data_files = list(build_emc.parent.glob("*.data"))
    if not data_files:
        raise RuntimeError(
            f"EMC finished but no .data file found in {build_emc.parent}"
        )
    data_path = max(data_files, key=lambda p: p.stat().st_mtime)

    # Strip force-field style lines from the .params file so the lammps-engine
    # templates control styles — keeping only pair_coeff/bond_coeff/etc. commands.
    # EMC writes pair_style/bond_style/etc. into .params which would override the
    # per-stage pair style (coul/cut vs coul/long) set by the .in templates.
    params_files = list(build_emc.parent.glob("*.params"))
    _style_prefixes = (
        "pair_style", "bond_style", "angle_style",
        "dihedral_style", "improper_style", "kspace_style",
    )
    for pf in params_files:
        lines = pf.read_text().splitlines(keepends=True)
        stripped = [l for l in lines if not any(l.startswith(p) for p in _style_prefixes)]
        if len(stripped) != len(lines):
            pf.write_text("".join(stripped))

    return data_path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_cell(
    smiles: str,
    output_dir: str | Path,
    output_name: str = "polymer",
    field: str = "pcff",
    density: float = 0.9,
    ntotal: int = 3000,
    dp: int = 20,
    nchains: int = 10,
    temperature: float = 300.0,
    seed: int = -1,
) -> Path:
    """
    Full pipeline: SMILES → .esh → emc_setup.pl → EMC binary → LAMMPS .data

    Parameters
    ----------
    smiles : str
        Repeat-unit SMILES with exactly two * connection points.
    output_dir : path-like
        Directory where all intermediate and output files are written.
    output_name : str
        Prefix for all generated files (default: "polymer").
    field : str
        EMC force field name (default: "pcff").
    density : float
        Target packing density in g/cm³. Use ~0.5× experimental for initial
        build to avoid overlaps; EMC scales to this density.
    ntotal : int
        Target total atom count. EMC chooses the number of chains to
        approximate this count given dp.
    dp : int
        Degree of polymerization — repeat units per chain.
    nchains : int
        Number of polymer chains. When set, overrides ntotal-based scaling.
        Pass 0 to let EMC determine chain count from ntotal (default path).
    temperature : float
        Build temperature in K (used for velocity assignments in the
        generated LAMMPS run script).
    seed : int
        Random seed for EMC. -1 selects a random seed each run.

    Returns
    -------
    Path
        Absolute path to the generated LAMMPS .data file.
    """
    _check_emc()

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use a fixed internal filename so emc_setup.pl's output-variable name
    # ("emc_build") never collides with the cluster name ("poly") in the .esh.
    esh_path = output_dir / "emc_build.esh"
    esh_path.write_text(
        make_esh(smiles, field=field, density=density, ntotal=ntotal, dp=dp)
    )

    build_emc = run_emc_setup(esh_path, field=field, seed=seed, temperature=temperature)
    data_path = run_emc_build(build_emc)
    return data_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Build a PCFF/EMC amorphous polymer cell from a repeat-unit SMILES."
    )
    parser.add_argument("smiles", help="Repeat-unit SMILES with two * connection points")
    parser.add_argument("output_dir", help="Directory to write all output files")
    parser.add_argument("--name", default="polymer", help="Output file prefix [polymer]")
    parser.add_argument("--field", default="pcff", help="EMC force field [pcff]")
    parser.add_argument("--density", type=float, default=0.9,
                        help="Target packing density in g/cm³ [0.9]")
    parser.add_argument("--ntotal", type=int, default=3000,
                        help="Target total atom count [3000]")
    parser.add_argument("--dp", type=int, default=20,
                        help="Repeat units per chain [20]")
    parser.add_argument("--nchains", type=int, default=10,
                        help="Number of chains (informational; EMC uses ntotal) [10]")
    parser.add_argument("--temperature", type=float, default=300.0,
                        help="Build temperature in K [300.0]")
    parser.add_argument("--seed", type=int, default=-1,
                        help="Random seed; -1 = random [-1]")
    parser.add_argument("--esh-only", action="store_true",
                        help="Write the .esh file and stop (do not run EMC)")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)

    if args.esh_only:
        output_dir.mkdir(parents=True, exist_ok=True)
        esh_path = output_dir / f"{args.name}.esh"
        esh_path.write_text(
            make_esh(
                args.smiles,
                field=args.field,
                density=args.density,
                ntotal=args.ntotal,
                dp=args.dp,
            )
        )
        print(f"Written: {esh_path}")
        return

    data_path = build_cell(
        smiles=args.smiles,
        output_dir=output_dir,
        output_name=args.name,
        field=args.field,
        density=args.density,
        ntotal=args.ntotal,
        dp=args.dp,
        nchains=args.nchains,
        temperature=args.temperature,
        seed=args.seed,
    )
    print(f"LAMMPS data file: {data_path}")


if __name__ == "__main__":
    main()
