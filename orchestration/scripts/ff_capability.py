#!/usr/bin/env python3
"""Which force fields can this installation actually run on this SMILES?

Field availability is two independent gates, and only both together make a field
a candidate:

  1. INTEGRATION — does the installed LAMMPS have every style the field's
     functional form needs? Checked against `lmp -h`, not against documentation.
  2. TYPING — can a front end assign this SMILES's atoms to the field's types and
     emit parameters? Checked by actually building, not by reading a coverage table.

Gate 1 is nearly always open: the installed KOKKOS binary covers five of the six
organic force fields LAMMPS documents (CHARMM, AMBER, COMPASS, DREIDING, OPLS),
plus Class II. Gate 2 is the real constraint — a field LAMMPS can integrate is
useless if nothing can type the monomer. CHARMM/CGenFF is the standing example:
fully runnable here, and untypeable from SMILES by EMC, which needs rule-based
typing where CHARMM uses residue templates.

This is a HARD gate and the only one in force-field selection that is. It says
which fields are possible, never which is accurate. Do not read a passing verdict
as an accuracy claim -- see ff_domain.py for why coverage does not predict error.

Prints JSON, always exits 0.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LMP = os.path.expanduser("~/lammps-install-kokkos/bin/lmp")
EMC_BUILDER = os.path.join(REPO, "mcp-servers", "mcp-emc-server", "smiles_to_emc.py")
MOL_PYTHON = os.path.expanduser("~/miniforge3/envs/mol-builder/bin/python")

# style requirements are the field's functional form, not a preference: a Class II
# field cannot be run with harmonic bonds. `pair` assumes long-range electrostatics,
# which every condensed-phase deck here uses.
FIELDS = {
    "pcff":             dict(front_end="emc", name="pcff",
                             styles=dict(pair="lj/class2/coul/long", bond="class2",
                                         angle="class2", dihedral="class2",
                                         improper="class2")),
    "pcff_ore":         dict(front_end="emc", name="pcff_ore",
                             styles=dict(pair="lj/class2/coul/long", bond="class2",
                                         angle="class2", dihedral="class2",
                                         improper="class2")),
    "compass":          dict(front_end="emc", name="compass",
                             styles=dict(pair="lj/class2/coul/long", bond="class2",
                                         angle="class2", dihedral="class2",
                                         improper="class2")),
    "opls/2024/opls-aa": dict(front_end="emc", name="opls/2024/opls-aa",
                             styles=dict(pair="lj/cut/coul/long", bond="harmonic",
                                         angle="harmonic", dihedral="opls",
                                         improper="cvff")),
    "opls/2012/opls-aa": dict(front_end="emc", name="opls/2012/opls-aa",
                             styles=dict(pair="lj/cut/coul/long", bond="harmonic",
                                         angle="harmonic", dihedral="opls",
                                         improper="cvff")),
    "trappe-ua":        dict(front_end="emc", name="trappe/2014/trappe-ua",
                             styles=dict(pair="lj/cut/coul/long", bond="harmonic",
                                         angle="harmonic", dihedral="opls")),
    "trappe-eh":        dict(front_end="emc", name="trappe/2014/trappe-eh",
                             styles=dict(pair="lj/cut/coul/long", bond="harmonic",
                                         angle="harmonic", dihedral="opls")),
    # CHARMM/CGenFF integrates fine; EMC cannot type a SMILES against it. Kept in
    # the registry so the typing failure is reported as a measured fact each run
    # rather than rediscovered by hand.
    "charmm/c36a":      dict(front_end="emc", name="charmm/c36a",
                             styles=dict(pair="lj/charmmfsw/coul/long", bond="harmonic",
                                         angle="charmm", dihedral="charmmfsw",
                                         improper="harmonic")),
    "gaff2":            dict(front_end="radonpy", name="gaff2",
                             styles=dict(pair="lj/cut/coul/long", bond="harmonic",
                                         angle="harmonic", dihedral="fourier",
                                         improper="cvff")),
    "gaff2_mod":        dict(front_end="radonpy", name="gaff2_mod",
                             styles=dict(pair="lj/cut/coul/long", bond="harmonic",
                                         angle="harmonic", dihedral="fourier",
                                         improper="cvff")),
    "gaff":             dict(front_end="radonpy", name="gaff",
                             styles=dict(pair="lj/cut/coul/long", bond="harmonic",
                                         angle="harmonic", dihedral="fourier",
                                         improper="cvff")),
    "dreiding":         dict(front_end="radonpy", name="dreiding",
                             styles=dict(pair="lj/cut/coul/long", bond="harmonic",
                                         angle="harmonic", dihedral="harmonic",
                                         improper="umbrella")),
}

# Present in ~/emc/field or radonpy but deliberately not candidates. Recorded so the
# next reader does not re-derive these by hand.
EXCLUDED = {
    "polystyrene": "coarse-grained inverse-Boltzmann tabulated potentials (kT vs metres, "
                   "no atom types, no .frc) — mesoscale, not an atomistic PS field",
    "cff":         "cannot type a SMILES — failed on polyethylene",
    "uff":         "cannot type a SMILES — failed on polyethylene",
    "charmm/iff":  "interface FF for inorganic surfaces; same residue-template typing "
                   "limit as charmm/c36a",
    "martini":     "coarse-grained",
    "sdk":         "coarse-grained (SDK/SPICA)",
    "dpd":         "dissipative particle dynamics — no atomistic density observable",
    "born":        "ionic Born-Mayer-Huggins, not molecular",
    "gauss":       "Gaussian core, not molecular",
    "amber":       "radonpy front end targets biomolecules; GAFF/GAFF2 are the "
                   "small-molecule/polymer members of the same family and are registered",
    "glycam":      "carbohydrate-specific",
    "tip":         "water models only",
}

_SECTIONS = ["Pair", "Bond", "Angle", "Dihedral", "Improper"]


def installed_styles(lmp=LMP):
    """{'pair': {...}, 'bond': {...}, ...} of style names the binary reports."""
    try:
        r = subprocess.run([lmp, "-h"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return {}
    # a truncated listing would report styles as missing rather than failing, in the
    # function that has already produced a false "everything is missing" once
    if r.returncode != 0:
        return {}
    out = r.stdout
    found, current = {}, None
    for line in out.splitlines():
        # a section runs until the next `* ... styles` header -- the blank line
        # directly under each header must not end it
        if line.startswith("*"):
            m = re.match(r"^\* (\w+) styles", line)
            current = m.group(1).lower() if m and m.group(1) in _SECTIONS else None
            if current:
                found[current] = set()
        elif current and line.strip():
            found[current].update(line.split())
    return found


def check_integration(field, styles):
    """Are every required style, and their KOKKOS variants, present?"""
    spec = FIELDS[field]["styles"]
    missing = [f"{kind}_style {name}" for kind, name in spec.items()
               if name not in styles.get(kind, set())]
    # a style with no /kk variant runs on the host under KOKKOS and forces a
    # host<->device copy every timestep, so this is a throughput cost, not a detail
    no_kk = [f"{kind}_style {name}" for kind, name in spec.items()
             if f"{name}/kk" not in styles.get(kind, set())]
    return {
        "integrates": not missing,
        "missing_styles": missing,
        "gpu_accelerated": (not no_kk) if not missing else None,
        "styles_without_kokkos": no_kk if not missing else None,
        "required_styles": spec,
    }


def _try_emc(smiles, name, workdir):
    # must actually run EMC: typing failures surface during the build, so --esh-only
    # (write the script and stop) would report success for every field
    cmd = [sys.executable, EMC_BUILDER, smiles, workdir, "--field", name,
           "--dp", "4", "--nchains", "2"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"{type(e).__name__}: {e}"
    if r.returncode == 0:
        return True, ""
    tail = (r.stderr or r.stdout or "").strip().splitlines()
    return False, " | ".join(tail[-3:])[:400]


_RADONPY_PROBE = """
import io, json, sys, contextlib
from radonpy.core import utils
from radonpy.ff.%(module)s import %(cls)s
try:
    mol = utils.mol_from_smiles(sys.argv[1])
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        ok = bool(%(cls)s().ff_assign(mol))
    print(json.dumps({"ok": ok, "err": "" if ok else "ff_assign returned False"}))
except Exception as e:
    print(json.dumps({"ok": False, "err": "%%s: %%s" %% (type(e).__name__, e)}))
"""

_RADONPY_CLS = {"gaff": ("gaff", "GAFF"), "gaff2": ("gaff2", "GAFF2"),
                "gaff2_mod": ("gaff2_mod", "GAFF2_mod"),
                "dreiding": ("dreiding", "Dreiding")}


def _try_radonpy(smiles, field):
    module, cls = _RADONPY_CLS[field]
    try:
        r = subprocess.run([MOL_PYTHON, "-c", _RADONPY_PROBE % dict(module=module, cls=cls),
                            smiles], capture_output=True, text=True, timeout=600)
        for line in reversed(r.stdout.splitlines()):
            if line.startswith("{"):
                d = json.loads(line)
                return d["ok"], d["err"][:400]
        return False, (r.stderr or "no JSON from probe").strip()[:400]
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return False, f"{type(e).__name__}: {e}"[:400]


def check_typing(smiles, field):
    """Try the front end for real -- never consult a coverage table.

    The two front ends prove DIFFERENT things and the caller must not conflate them:
    EMC builds an actual cell, so success means a runnable system. RadonPy's
    ff_assign only proves atom types and bonded parameters were assigned; a runnable
    GAFF2 cell additionally needs the per-chemistry QM charge step, which this does
    not run. `typing_evidence` records which standard was met.
    """
    spec = FIELDS[field]
    if spec["front_end"] == "emc":
        workdir = tempfile.mkdtemp(prefix=f"ffcap_{field.replace('/', '_')}_")
        try:
            ok, err = _try_emc(smiles, spec["name"], workdir)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
        evidence = "built_cell"
    else:
        ok, err = _try_radonpy(smiles, field)
        evidence = "typed_only"
    return {"types_smiles": ok, "front_end": spec["front_end"], "typing_error": err,
            "typing_evidence": evidence if ok else None,
            "further_steps_required": (["QM charge assignment (per chemistry)"]
                                       if ok and evidence == "typed_only" else [])}


def assess_all(smiles, fields=None, lmp=LMP):
    styles = installed_styles(lmp)
    if not styles:
        return {"error": f"could not read styles from {lmp}"}
    results = {}
    for field in (fields or sorted(FIELDS)):
        integ = check_integration(field, styles)
        # typing is the expensive half -- skip it when the field cannot run anyway
        typ = (check_typing(smiles, field) if integ["integrates"]
               else {"types_smiles": None, "front_end": FIELDS[field]["front_end"],
                     "typing_error": "not attempted — field does not integrate",
                     "typing_evidence": None, "further_steps_required": []})
        results[field] = dict(integ, **typ)
        results[field]["candidate"] = bool(integ["integrates"] and typ["types_smiles"])
    cands = sorted(f for f, r in results.items() if r["candidate"])
    return {
        "smiles": smiles,
        "fields": results,
        "candidates": cands,
        "candidates_built_cell": [f for f in cands
                                  if results[f]["typing_evidence"] == "built_cell"],
        "candidates_typed_only": [f for f in cands
                                  if results[f]["typing_evidence"] == "typed_only"],
        "note": ("A candidate is a field this installation can integrate AND whose front "
                 "end accepted this SMILES. Evidence differs: candidates_built_cell were "
                 "built to a runnable cell; candidates_typed_only were only typed, and "
                 "still need the steps in further_steps_required. It is NOT a claim about "
                 "accuracy — rank candidates by the archive prior and the reference-free "
                 "comparators, never by this verdict."),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("smiles", nargs="?", help="repeat-unit SMILES with two * connection points")
    p.add_argument("--fields", help="comma-separated subset of fields to test")
    p.add_argument("--lmp", default=LMP, help="LAMMPS binary to probe for styles")
    p.add_argument("--integration-only", action="store_true",
                   help="report style availability only, no build attempts")
    args = p.parse_args()

    try:
        fields = args.fields.split(",") if args.fields else None
        if bad := [f for f in (fields or []) if f not in FIELDS]:
            result = {"error": f"unknown fields {bad}. Known: {sorted(FIELDS)}"}
        elif args.integration_only:
            styles = installed_styles(args.lmp)
            result = ({"error": f"could not read styles from {args.lmp}"} if not styles
                      else {"fields": {f: check_integration(f, styles)
                                       for f in (fields or sorted(FIELDS))}})
        elif not args.smiles:
            result = {"error": "smiles is required unless --integration-only"}
        else:
            result = assess_all(args.smiles, fields, args.lmp)
    except Exception as e:  # noqa: BLE001 — callers parse JSON, never a traceback
        result = {"error": f"{type(e).__name__}: {e}"}

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
