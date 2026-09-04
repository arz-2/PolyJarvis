#!/usr/bin/env python3
"""
forcefield.py — force-field selection and everything the choice rests on.

D-01_ff is not one question but four, and each used to be its own file: can this force field
even type this monomer and run in this LAMMPS build (capability), is this monomer's chemistry
inside the field's validated vocabulary (domain), did the parameters that actually got written
come from the stock field or a local patch (provenance), and which EMC field files are we
running against (emc fields). select_forcefield() is the only one of the five that anything
outside ever imported -- the other four existed to be read in sequence by whoever was trying to
answer "why did this run get PCFF?".

Merged 2026-09-02 (select_forcefield.py, ff_capability.py, ff_domain.py, ff_provenance.py,
emc_fields.py). Two name clashes were resolved rather than papered over:
  - assess()  existed in both ff_domain and ff_provenance meaning different things; they are
              now assess_domain() and assess_provenance().
  - _ARITY    was LAMMPS coeff kinds in ff_provenance and EMC field-file section names in
              emc_fields -- genuinely different tables, now _LAMMPS_COEFF_ARITY and
              _EMC_SECTION_ARITY.
Merging emc_fields.py also removes a latent shadowing hazard: it shared a name with the
repo-root emc_fields/ directory, and only won `import emc_fields` because this scripts
directory is pushed to the front of sys.path.

Subcommands: select (D-01), capability, domain, provenance, emc-fields.
Sections below run low-level to high: EMC FIELD FILES -> CAPABILITY -> PROVENANCE -> DOMAIN
-> SELECTION -> CLI.
"""
import argparse
import collections
import fnmatch
import glob
import hashlib
import itertools
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rules_common import load_rules, get_class_entry  # noqa: E402
from mol_python import run_in_mol_env  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EMC_ROOT = os.environ.get("EMC_ROOT", os.path.expanduser("~/emc"))
MANIFEST = os.path.join(REPO, "emc_fields", "manifest.json")
LMP = os.path.expanduser("~/lammps-install-kokkos/bin/lmp")
EMC_BUILDER = os.path.join(REPO, "mcp-servers", "mcp-emc-server", "smiles_to_emc.py")


# ===========================================================================
# EMC FIELD FILES  (`emc-fields`)
#
# Local modifications to the installed EMC field tree.
#
# EMC's field files live outside this repo (~/emc/field) and have been hand-edited.
# An edit there changes what a polymer is built from with no git diff, and a reinstall
# silently reverts it. emc_fields/ holds the vendor baseline, the diffs, and the hashes
# of both states; this script is the only thing that reads them.
#
#   --verify        installed tree matches the manifest        (exit 1 on mismatch)
#   --apply         re-apply the patches to a fresh install
#   --patched-rows  parameter rows this installation added or changed, by section
#                   — the input ff_provenance.py uses to tell a locally authored
#                   parameter from a vendor one
#
# Prints JSON.
# ===========================================================================
_EMC_SECTION_ARITY = {"INCREMENT": 2, "NONBOND": 1, "BOND": 2, "ANGLE": 3, "ANGLE_AUTO": 3,
          "TORSION": 4, "TORSION_AUTO": 4, "IMPROPER": 4, "IMPROPER_AUTO": 4,
          "EQUIVALENCE": 1, "MASS": 1}


def _sha256(path):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
    except OSError:
        return None
    return h.hexdigest()


def load_manifest(path=MANIFEST):
    with open(path) as fh:
        return json.load(fh)


def _installed_path(field, basename, emc_root=EMC_ROOT):
    return os.path.join(emc_root, "field", os.path.dirname(field), basename)


def verify(manifest, emc_root=EMC_ROOT):
    """Does the installed tree match a state the manifest knows about?"""
    out = {"emc_root": emc_root, "fields": {}, "ok": True}
    for field, spec in manifest["fields"].items():
        for basename, f in spec["files"].items():
            p = _installed_path(field, basename, emc_root)
            got = _sha256(p)
            if got == f["sha256_patched"]:
                state = "patched"
            elif got == f["sha256_stock"]:
                state = "stock"
            elif got is None:
                state = "missing"
            else:
                state = "unknown"
            out["fields"][f"{field}/{basename}"] = {"state": state, "sha256": got,
                                                    "path": p}
            if state != "patched":
                out["ok"] = False
    out["reason"] = ("every patched field file is present and matches the manifest"
                     if out["ok"] else
                     "at least one field file is stock, missing, or modified outside "
                     "this manifest — a build from this tree does not use the "
                     "parameters recorded here")
    return out


def apply_patches(manifest, emc_root=EMC_ROOT, dry_run=False):
    """Re-apply the vendored patches to a fresh EMC install."""
    if not shutil.which("patch"):
        return {"applied": [], "error": "`patch` not on PATH"}
    out = {"emc_root": emc_root, "applied": [], "skipped": [], "failed": []}
    for field, spec in manifest["fields"].items():
        for basename, f in spec["files"].items():
            p = _installed_path(field, basename, emc_root)
            got = _sha256(p)
            if got == f["sha256_patched"]:
                out["skipped"].append({"file": p, "reason": "already patched"})
                continue
            if got != f["sha256_stock"]:
                out["failed"].append({"file": p, "reason": (
                    "not the stock baseline this patch was made against — refusing to "
                    "patch a file whose contents are unknown")})
                continue
            cmd = ["patch", "--forward", "--silent"] + (["--dry-run"] if dry_run else [])
            r = subprocess.run(cmd + [p, os.path.join(REPO, f["patch"])],
                               capture_output=True, text=True)
            (out["applied"] if r.returncode == 0 else out["failed"]).append(
                {"file": p, **({} if r.returncode == 0
                               else {"reason": (r.stderr or r.stdout).strip()[:300]})})
    out["ok"] = not out["failed"]
    return out


def _added_lines(stock_path, installed_path):
    """Lines present in the installed file that the stock baseline does not have.

    Compared as a multiset-free set of stripped lines: a parameter row is unique by
    its type tuple within a section, so a duplicate line is not a case that arises.
    """
    def _read(p):
        try:
            with open(p) as fh:
                return {ln.rstrip("\n") for ln in fh if ln.strip()
                        and not ln.lstrip().startswith("#")}
        except OSError:
            return set()
    return _read(installed_path) - _read(stock_path)


def patched_rows(manifest, field, emc_root=EMC_ROOT):
    """{section: [type tuple, ...]} for rows this installation added or changed."""
    spec = manifest["fields"][field]
    result = {"field": field, "sections": {}, "typing_rules": []}
    for basename, f in spec["files"].items():
        stock = os.path.join(REPO, f["stock"])
        inst = _installed_path(field, basename, emc_root)
        added = _added_lines(stock, inst)
        if not added:
            continue
        if not basename.endswith(".prm"):
            # .top / .define rows are typing rules; column 1 (.define) or 2 (.top)
            # names the type
            for ln in sorted(added):
                cols = ln.split()
                if cols:
                    result["typing_rules"].append(cols[1] if cols[0].isdigit() else cols[0])
            continue
        section = None
        try:
            with open(inst) as fh:
                for ln in fh:
                    s = ln.rstrip("\n")
                    t = s.split()
                    if t[:1] == ["ITEM"] and len(t) > 1:
                        section = None if t[1] == "END" else t[1]
                        continue
                    if section and s in added:
                        n = _EMC_SECTION_ARITY.get(section)
                        if n:
                            result["sections"].setdefault(section, []).append(t[:n])
        except OSError:
            continue
    result["typing_rules"] = sorted(set(result["typing_rules"]))
    result["n_rows"] = sum(len(v) for v in result["sections"].values())
    return result


# ===========================================================================
# CAPABILITY  (`capability`)
#
# Which force fields can this installation actually run on this SMILES?
#
# Field availability is two independent gates, and only both together make a field
# a candidate:
#
#   1. INTEGRATION — does the installed LAMMPS have every style the field's
#      functional form needs? Checked against `lmp -h`, not against documentation.
#   2. TYPING — can a front end assign this SMILES's atoms to the field's types and
#      emit parameters? Checked by actually building, not by reading a coverage table.
#
# Gate 1 is nearly always open: the installed KOKKOS binary covers five of the six
# organic force fields LAMMPS documents (CHARMM, AMBER, COMPASS, DREIDING, OPLS),
# plus Class II. Gate 2 is the real constraint — a field LAMMPS can integrate is
# useless if nothing can type the monomer. CHARMM/CGenFF is the standing example:
# fully runnable here, and untypeable from SMILES by EMC, which needs rule-based
# typing where CHARMM uses residue templates.
#
# This is a HARD gate and the only one in force-field selection that is. It says
# which fields are possible, never which is accurate. Do not read a passing verdict
# as an accuracy claim -- see ff_domain.py for why coverage does not predict error.
#
# Prints JSON, always exits 0.
# ===========================================================================
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
    # United-atom OPLS, present in ~/emc/field/opls/{2012,2024}/opls-ua.* but never
    # previously registered here, so it was never assessed as a D-01 candidate.
    # Confirmed by reading both .prm files directly: neither carries a final
    # `ITEM IMPROPER` params list (2012 has only IMPROPER_AUTO derivation rules,
    # 2024 has none at all), so -- unlike opls-aa -- no improper style is required,
    # matching the trappe-ua/trappe-eh pattern below.
    "opls/2024/opls-ua": dict(front_end="emc", name="opls/2024/opls-ua",
                             styles=dict(pair="lj/cut/coul/long", bond="harmonic",
                                         angle="harmonic", dihedral="opls")),
    "opls/2012/opls-ua": dict(front_end="emc", name="opls/2012/opls-ua",
                             styles=dict(pair="lj/cut/coul/long", bond="harmonic",
                                         angle="harmonic", dihedral="opls")),
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
        r = run_in_mol_env(script=_RADONPY_PROBE % dict(module=module, cls=cls),
                            args=[smiles], env="mol-builder", timeout=600)
        for line in reversed(r.stdout.splitlines()):
            if line.startswith("{"):
                d = json.loads(line)
                return d["ok"], d["err"][:400]
        return False, (r.stderr or "no JSON from probe").strip()[:400]
    except (OSError, subprocess.SubprocessError, ValueError) as e:
        return False, f"{type(e).__name__}: {e}"[:400]


def check_typing(smiles, field, keep_dir=None):
    """Try the front end for real -- never consult a coverage table.

    The two front ends prove DIFFERENT things and the caller must not conflate them:
    EMC builds an actual cell, so success means a runnable system. RadonPy's
    ff_assign only proves atom types and bonded parameters were assigned; a runnable
    GAFF2 cell additionally needs the per-chemistry QM charge step, which this does
    not run. `typing_evidence` records which standard was met.

    `keep_dir` retains the built cell there instead of discarding it, so a caller that
    wants to inspect the emitted parameters does not pay for a second build.
    """
    spec = FIELDS[field]
    cell_dir = None
    if spec["front_end"] == "emc":
        if keep_dir:
            cell_dir = os.path.join(keep_dir, field.replace("/", "_"))
            os.makedirs(cell_dir, exist_ok=True)
            ok, err = _try_emc(smiles, spec["name"], cell_dir)
        else:
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
            "cell_dir": cell_dir if ok else None,
            "further_steps_required": (["QM charge assignment (per chemistry)"]
                                       if ok and evidence == "typed_only" else [])}


def assess_all(smiles, fields=None, lmp=LMP, keep_dir=None):
    styles = installed_styles(lmp)
    if not styles:
        return {"error": f"could not read styles from {lmp}"}
    results = {}
    for field in (fields or sorted(FIELDS)):
        integ = check_integration(field, styles)
        # typing is the expensive half -- skip it when the field cannot run anyway
        typ = (check_typing(smiles, field, keep_dir) if integ["integrates"]
               else {"types_smiles": None, "front_end": FIELDS[field]["front_end"],
                     "typing_error": "not attempted — field does not integrate",
                     "typing_evidence": None, "cell_dir": None,
                     "further_steps_required": []})
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


# ===========================================================================
# PROVENANCE  (`provenance`)
#
# Where did this cell's force-field parameters actually come from?
#
# A field that types a molecule can still be wrong for it, because the numbers it used
# were not fitted for this chemistry. EMC never says so: it writes a parameter file and
# exits 0 whether a row came from the published field, from a wildcard fallback, from a
# local hand-edit, or from a silent zero substituted for a row that does not exist.
#
# This reads a built cell's emc_build.params -- every emitted `*_coeff` row carries its
# type tuple as a trailing comment -- and resolves each tuple back against the installed
# field file:
#
#   LOCAL_PATCH       the row was added or changed on this machine (emc_fields.py)
#   ZERO_SUBSTITUTED  all-zero parameters AND no source row -- EMC filled in a zero
#   AUTO_FALLBACK     matched only a wildcard/_auto section, not a specific row
#   NO_SOURCE_ROW     nonzero parameters no source row explains -- a lookup bug here,
#                     not a defect in the field; this flag is the parser's self-test
#
# SCOPE: this checks whether a source row EXISTS, not whether the emitted number equals
# it. Reproducing EMC's values means reproducing its unit conversions and Class II
# cross-term arithmetic, which would trade a reliable existence check for an unreliable
# equality one. A wrong-but-present parameter is out of scope and stays out.
#
# Prints JSON, always exits 0 -- callers transcribe the verdict.
# ===========================================================================
_LAMMPS_COEFF_ARITY = {"pair": 1, "bond": 2, "angle": 3, "torsion": 4, "improper": 4}

_HEADER_RE = re.compile(r"^#\s*(\w+)\s+Coeffs\s*$")
_COEFF_RE = re.compile(r"^\s*(\w+)_coeff\s+(.*?)\s*#\s*([^\s#]+)\s*$")


def parse_params(path):
    """[{kind, section, index, params, types}] for every coeff row in emc_build.params."""
    rows, section = [], None
    with open(path) as fh:
        for line in fh:
            h = _HEADER_RE.match(line.strip())
            if h:
                section = h.group(1)
                continue
            m = _COEFF_RE.match(line)
            if not m:
                continue
            prefix, cols, comment = m.group(1), m.group(2).split(), m.group(3)
            # pair_coeff is `i j <params>`, everything else `<id> [sub-tag] <params>`
            n_id = 2 if prefix == "pair" else 1
            rows.append({
                "kind": _KINDS.get(section),
                "section": section,
                "prefix": prefix,
                "index": " ".join(cols[:n_id]),
                "params": [float(c) for c in cols[n_id:] if _is_num(c)],
                "types": comment.split(","),
            })
    return rows


def _is_num(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


class _Field:
    """Existence lookup over one installed field file."""

    def lookup(self, kind, types):
        """('specific'|'auto'|None) for this type tuple."""
        # a pair_coeff comment names both indices (`# c,c`) but a nonbond section is
        # keyed on a single type: every named type must resolve
        if kind == "pair":
            uniq = sorted(set(types))
            found = [self._lookup(kind, [t]) for t in uniq]
            return None if None in found else ("auto" if "auto" in found else "specific")
        return self._lookup(kind, types)

    def _lookup(self, kind, types):
        for source in ("specific", "auto"):
            eq = self.equivalents(types, kind, source)
            for row in self._rows(kind, source):
                if _match(eq, row) or _match(list(reversed(eq)), row):
                    return source
            if kind == "improper" and self._improper_permutation_match(eq, source):
                return source
        return None

    def equivalents(self, types, kind, source):
        return [self.equivalent(t, kind) for t in types]

    def _improper_permutation_match(self, eq, source):
        # An out-of-plane term names a centre and three substituents, and neither the
        # centre's position nor the substituent order is shared between EMC's comment
        # and the field file: EMC writes the centre first, .frc wilson rows write it
        # second, and the field stores only one canonical substituent order (cis-PBD
        # emits both `c=2,c,c=2,hc` and `c=2,c,hc,c=2` against a single `c c= c= h`
        # row). Try every centre in either position with the substituents in any order.
        rows = list(self._rows("improper", source))
        if not rows:
            return False
        for c in range(len(eq)):
            rest = [t for i, t in enumerate(eq) if i != c]
            for perm in itertools.permutations(rest):
                for cand in ([eq[c]] + list(perm), [perm[0], eq[c]] + list(perm[1:])):
                    if any(_match(cand, row) for row in rows):
                        return True
        return False


def _match(types, row):
    return len(types) == len(row) and all(_tok(t, r) for t, r in zip(types, row))


def _tok(atom_type, pattern):
    # two wildcard conventions coexist: .frc _auto rows use a leading `*` (and the
    # numbered `*1`/`*2`/... variants, which are distinct rows but all match anything),
    # while .prm _AUTO rows use trailing globs like `c4*`
    if pattern.startswith("*"):
        return True
    if "*" in pattern:
        return fnmatch.fnmatchcase(atom_type, pattern)
    return pattern == atom_type


class PrmField(_Field):
    """EMC .prm -- ITEM-delimited, tab separated (OPLS, TraPPE)."""

    _SECTIONS = {"pair": ("NONBOND", None), "bond": ("BOND", "BOND_AUTO"),
                 "angle": ("ANGLE", "ANGLE_AUTO"), "torsion": ("TORSION", "TORSION_AUTO"),
                 "improper": ("IMPROPER", "IMPROPER_AUTO")}
    # ITEM EQUIVALENCE columns: type pair incr bond angle torsion improper
    _EQ_COL = {"pair": 1, "bond": 3, "angle": 4, "torsion": 5, "improper": 6}

    def __init__(self, path):
        self.sections, self.eq = {}, {}
        section = None
        with open(path) as fh:
            for line in fh:
                s = line.rstrip("\n")
                if not s.strip() or s.lstrip().startswith("#"):
                    continue
                t = s.split()
                if t[0] == "ITEM":
                    section = None if t[1] == "END" else t[1]
                    continue
                if section == "EQUIVALENCE":
                    self.eq[t[0]] = t
                elif section:
                    self.sections.setdefault(section, []).append(t)

    def equivalent(self, atom_type, kind):
        row = self.eq.get(atom_type)
        col = self._EQ_COL.get(kind)
        return row[col] if row and col is not None and col < len(row) else atom_type

    def _rows(self, kind, source):
        name = self._SECTIONS.get(kind, (None, None))[0 if source == "specific" else 1]
        n = _LAMMPS_COEFF_ARITY[kind]
        for row in self.sections.get(name or "", []):
            yield row[:n]


class FrcField(_Field):
    """Biosym .frc -- #-delimited, rows prefixed `Ver Ref` (PCFF, COMPASS)."""

    _SECTIONS = {
        "pair":     ("nonbond(9-6)", None),
        "bond":     ("quartic_bond", "quadratic_bond"),
        "angle":    ("quartic_angle", "quadratic_angle"),
        "torsion":  ("torsion_3", "torsion_1"),
        "improper": ("wilson_out_of_plane", "wilson_out_of_plane"),
    }
    # #equivalence columns: Ver Ref Type NonB Bond Angle Torsion OOP
    _EQ_COL = {"pair": 3, "bond": 4, "angle": 5, "torsion": 6, "improper": 7}
    # #auto_equivalence is position-dependent -- a bonded term's end atoms and its
    # centre/apex atoms map through different columns:
    #   Ver Ref Type NonB Bond BondInct AngleEnd AngleApex TorsEnd TorsCentre OOPEnd OOPCentre
    # bond uses column 5, not 4: the _auto sections are keyed on the underscored
    # forms (`c'_`, `cp_`), which is where those live regardless of the header labels
    _AUTO_COL = {"pair": (3, 3), "bond": (5, 5), "angle": (6, 7),
                 "torsion": (8, 9), "improper": (10, 11)}
    # which positions in a tuple of this kind are "centre" atoms
    _CENTRE_POS = {"angle": {1}, "torsion": {1, 2}, "improper": {1}}

    def __init__(self, path):
        self.sections, self.eq, self.auto_eq = {}, {}, {}
        key = None
        with open(path) as fh:
            for line in fh:
                s = line.rstrip("\n")
                if s.startswith("#"):
                    t = s[1:].split()
                    key = (t[0], t[1] if len(t) > 1 else "") if t else None
                    continue
                if not s.strip() or s.lstrip()[0] in "!>":
                    continue
                t = s.split()
                if not key or len(t) < 3:
                    continue
                if key[0] == "equivalence":
                    self.eq[t[2]] = t
                elif key[0] == "auto_equivalence":
                    self.auto_eq[t[2]] = t
                else:
                    self.sections.setdefault(key, []).append(t)

    def equivalent(self, atom_type, kind):
        row = self.eq.get(atom_type)
        col = self._EQ_COL.get(kind)
        return row[col] if row and col is not None and col < len(row) else atom_type

    def equivalents(self, types, kind, source):
        if source != "auto":
            return [self.equivalent(t, kind) for t in types]
        end_col, centre_col = self._AUTO_COL.get(kind, (None, None))
        centre = self._CENTRE_POS.get(kind, set())
        out = []
        for i, t in enumerate(types):
            row = self.auto_eq.get(t)
            col = centre_col if i in centre else end_col
            out.append(row[col] if row and col is not None and col < len(row) else t)
        return out

    def _rows(self, kind, source):
        name = self._SECTIONS.get(kind, (None, None))[0 if source == "specific" else 1]
        if not name:
            return
        n = _LAMMPS_COEFF_ARITY[kind]
        for key, rows in self.sections.items():
            if key[0] != name:
                continue
            is_auto = key[1].endswith("_auto")
            if is_auto != (source == "auto"):
                continue
            for row in rows:
                yield row[2:2 + n]      # skip Ver, Ref


def open_field(field, emc_root=EMC_ROOT):
    """A reader for an installed field name, e.g. 'pcff' or 'opls/2024/opls-aa'.

    A run plan records the short key ('trappe-ua'); the installed tree uses the path
    ff_capability's registry already maps it to.
    """
    field = FIELDS.get(field, {}).get("name", field)
    base = os.path.join(emc_root, "field", field)
    if os.path.exists(base + ".prm"):
        return PrmField(base + ".prm"), base + ".prm"
    frc = os.path.join(emc_root, "field", field, os.path.basename(field) + ".frc")
    if os.path.exists(frc):
        return FrcField(frc), frc
    raise FileNotFoundError(f"no .prm or .frc for field {field!r} under {emc_root}")


def _patched_index(field, emc_root):
    """{(kind, frozenset-ordered tuple)} of locally added rows, and the increments."""
    try:
        m = load_manifest()
        if field not in m["fields"]:
            return set(), []
        pr = patched_rows(m, field, emc_root)
    except Exception:  # noqa: BLE001 — absent manifest must not fail the whole check
        return set(), []
    kind_of = {"BOND": "bond", "ANGLE": "angle", "TORSION": "torsion",
               "IMPROPER": "improper", "NONBOND": "pair"}
    rows = {(kind_of[s], tuple(t)) for s, ts in pr["sections"].items()
            if s in kind_of for t in ts}
    rows |= {(k, tuple(reversed(t))) for k, t in rows}
    return rows, pr["sections"].get("INCREMENT", [])


def assess_provenance(cell_dir, field, emc_root=EMC_ROOT):
    params = os.path.join(cell_dir, "emc_build.params")
    if not os.path.exists(params):
        return {"error": f"no emc_build.params under {cell_dir}"}
    reader, field_path = open_field(field, emc_root)
    patched, patched_incr = _patched_index(field, emc_root)

    findings, unchecked = [], {}
    checked = 0
    for row in parse_params(params):
        if row["kind"] is None:
            key = row["section"] or row["prefix"]
            unchecked[key] = unchecked.get(key, 0) + 1
            continue
        checked += 1
        kind, types = row["kind"], row["types"]
        reasons = []
        if (kind, tuple(types)) in patched:
            reasons.append("LOCAL_PATCH")
        source = reader.lookup(kind, types)
        all_zero = bool(row["params"]) and all(p == 0.0 for p in row["params"])
        if source is None:
            reasons.append("ZERO_SUBSTITUTED" if all_zero else "NO_SOURCE_ROW")
        elif source == "auto":
            reasons.append("AUTO_FALLBACK")
        if reasons:
            findings.append({
                "flags": reasons,
                "kind": kind,
                "types": types,
                "coeff": f"{row['prefix']}_coeff {row['index']}",
                "params": row["params"],
                "source": source,
                "severity": _severity(reasons, kind),
            })

    present = {t for row in parse_params(params) for t in row["types"]}
    incr = [i for i in patched_incr if set(i) <= present]
    return {
        "cell_dir": cell_dir,
        "field": field,
        "field_file": field_path,
        "rows_checked": checked,
        "unchecked_cross_terms": unchecked,
        "local_patch_increments": incr,
        "findings": sorted(findings, key=lambda f: (f["severity"] != "blocking",
                                                    f["kind"], f["types"])),
        "counts": _counts(findings),
        "parser_gaps": sum(1 for f in findings if f["severity"] == "self_check"),
        "verdict": ("FF_PROVENANCE_BLOCKING"
                    if any(f["severity"] == "blocking" for f in findings) or incr
                    else "FF_PROVENANCE_ADVISORY" if findings
                    else "FF_PROVENANCE_CLEAN"),
        "note": ("Existence check only — a source row was found or it was not. This does "
                 "not verify the emitted value equals the field's. NO_SOURCE_ROW on a "
                 "nonzero row means the lookup missed, which is a bug here, not a "
                 "finding about the field."),
    }


def _severity(reasons, kind):
    # NO_SOURCE_ROW is a statement about THIS parser, not about the field. It must be
    # loud, but it must never demote a candidate or block a plan -- a gap in the lookup
    # would otherwise silently change which force field a run uses.
    if "NO_SOURCE_ROW" in reasons and "LOCAL_PATCH" not in reasons:
        return "self_check"
    if "LOCAL_PATCH" in reasons:
        return "blocking"
    if "ZERO_SUBSTITUTED" in reasons:
        # a zero out-of-plane term is the norm for sp3 centres and appears in every
        # archived cell; a zeroed torsion is a statement about chain stiffness
        return "advisory" if kind == "improper" else "blocking"
    return "advisory"


def _counts(findings):
    out = {}
    for f in findings:
        for flag in f["flags"]:
            out[flag] = out.get(flag, 0) + 1
    return out


# ===========================================================================
# DOMAIN  (`domain`)
#
# Is this polymer inside a force field's demonstrated domain?
#
# A classical force field's accuracy lives in its per-atom-type parameters, so the
# question that can be answered without experimental data is not "is this field
# correct" but "has this field already been validated on the types this molecule is
# built from".
#
# Measured on the archive, PCFF's validated vocabulary is 15 types across 7 families,
# and the overlap is high -- PEG, PMMA and PS introduce no type the others do not
# already cover; PEEK, PLA, PSU and PVC add one or two each.
#
# THIS IS A PROVENANCE SIGNAL, NOT AN ACCURACY PREDICTOR. It answers "has this field
# been exercised on this chemistry in a completed run here", which is a fact about
# what a prior is worth, not a forecast of error. Backtested leave-one-family-out
# against measured error on this archive, extrapolation does NOT predict inaccuracy:
#
#     corr(extrapolated atom fraction, |K error|)       = -0.26
#     corr(extrapolated atom fraction, |density error|) = -0.64   (n=6)
#
# Both are negative -- more extrapolation went with *better* agreement, largely
# because TraPPE-UA's small validated vocabulary makes its two accurate families look
# maximally extrapolating. The counter-examples are direct: PLA extrapolates on 0.2%
# of its atoms and has the archive's worst K error (+33%); cis-PBD extrapolates on
# 49.8% and has among its best densities (-0.2%).
#
# So: report this verdict, never gate on it. Using it to discard a candidate field
# would have thrown out TraPPE-UA for cis-PBD -- the most accurate density in the
# whole archive. Accuracy has to be decided by the reference-free comparators and the
# cross-field spread, not here.
#
# Runs at build time, before any long simulation. Prints JSON, always exits 0 --
# callers transcribe the verdict rather than re-deriving it.
# ===========================================================================
# `mass  <id>   <mass>  # <type_name>` in an EMC-written params file
_MASS_RE = re.compile(r"^\s*mass\s+(\d+)\s+[\d.eE+-]+\s*#\s*([A-Za-z0-9_+-]+)")


def types_from_params(params_path):
    """{type_id: type_name} from an emc_build.params file. {} if unreadable."""
    out = {}
    try:
        with open(params_path) as fh:
            for line in fh:
                m = _MASS_RE.match(line)
                if m:
                    out[int(m.group(1))] = m.group(2)
    except OSError:
        return {}
    return out


def abundance_from_data(data_path, id_to_name):
    """{type_name: atom_count} from a LAMMPS .data Atoms section.

    Returns {} when the file is missing, so callers fall back to unweighted
    coverage rather than failing.
    """
    counts = collections.Counter()
    section = None
    try:
        with open(data_path) as fh:
            for line in fh:
                head = line.split("#")[0].strip()
                if head in ("Masses", "Atoms", "Velocities", "Bonds", "Angles",
                            "Dihedrals", "Impropers", "Pair Coeffs", "Bond Coeffs"):
                    section = head
                    continue
                if section != "Atoms" or not head:
                    continue
                t = head.split()
                if len(t) >= 7:               # full: id mol type q x y z [ix iy iz]
                    try:
                        counts[id_to_name.get(int(t[2]))] += 1
                    except ValueError:
                        pass
    except OSError:
        return {}
    counts.pop(None, None)
    return dict(counts)


def cell_fingerprint(cell_dir):
    """Types and per-type atom fractions for one built cell."""
    params = os.path.join(cell_dir, "emc_build.params")
    id_to_name = types_from_params(params)
    if not id_to_name:
        return None
    abundance = abundance_from_data(os.path.join(cell_dir, "cell.data"), id_to_name)
    total = sum(abundance.values())
    return {
        "types": sorted(set(id_to_name.values())),
        "atom_fraction": ({k: round(v / total, 4) for k, v in abundance.items()}
                          if total else {}),
        "n_atoms": total,
    }


def _field_of_run(run_dir):
    """decided_params.preferred_ff for an archived run, or None."""
    for rel in ("raw/run_plan.json", "run_plan.json"):
        try:
            with open(os.path.join(run_dir, rel)) as fh:
                return json.load(fh).get("decided_params", {}).get("preferred_ff")
        except (OSError, ValueError):
            continue
    return None


def build_vocabulary(archive_root):
    """{field: {type: [families that exercised it]}} from validated archived runs.

    A type counts as validated only if a completed run actually used it -- the
    field file may define thousands more that have never been exercised here.
    """
    vocab = collections.defaultdict(lambda: collections.defaultdict(set))
    for params in sorted(glob.glob(os.path.join(archive_root, "*", "lammps", "cell",
                                                "emc_build.params"))):
        run_dir = params.split(os.sep + "lammps" + os.sep)[0]
        run = os.path.basename(run_dir)
        field = _field_of_run(run_dir)
        if not field:
            continue
        family = re.sub(r"\d+$", "", run)
        for name in set(types_from_params(params).values()):
            vocab[field][name].add(family)
    return {f: {t: sorted(fams) for t, fams in d.items()} for f, d in vocab.items()}


def assess_domain(fingerprint, vocabulary, field):
    """Verdict for one (cell, field) pair."""
    known = vocabulary.get(field)
    if not known:
        return {
            "verdict": "FF_UNAVAILABLE",
            "field": field,
            "reason": (f"no validated run in the archive used field '{field}', so it has no "
                       "demonstrated domain here — every type is an extrapolation"),
            "validated_fields": sorted(vocabulary),
        }
    types = set(fingerprint["types"])
    new = sorted(types - set(known))
    frac = fingerprint.get("atom_fraction") or {}
    new_atom_fraction = round(sum(frac.get(t, 0.0) for t in new), 4) if frac else None

    out = {
        "verdict": "FF_IN_DOMAIN" if not new else "FF_EXTRAPOLATING",
        "field": field,
        "n_types": len(types),
        "n_validated": len(types) - len(new),
        "type_coverage": round((len(types) - len(new)) / len(types), 4) if types else None,
        "extrapolated_types": new,
        "extrapolated_atom_fraction": new_atom_fraction,
        "validated_vocabulary_size": len(known),
    }
    out["is_accuracy_prediction"] = False
    if new:
        out["validated_types_present"] = {t: known[t] for t in sorted(types & set(known))}
        out["reason"] = (
            f"{len(new)} of {len(types)} types have never been exercised under '{field}' in a "
            f"completed run: {new}. This weakens the PROVENANCE of any accuracy prior carried "
            "over from the archive. It is NOT a prediction that this run will be inaccurate — "
            "extrapolation does not correlate with error on this archive (see module docstring). "
            "Do not discard this field on this verdict alone."
        )
    else:
        out["reason"] = (
            f"every type is covered by completed '{field}' runs, so an accuracy prior from the "
            "archive is at least on-domain. That is a statement about provenance, not a "
            "guarantee of agreement — the field's known bias still applies."
        )
    return out


# ===========================================================================
# SELECTION — D-01_ff  (`select`)
#
# Mechanically select D-01_ff from policy + measured admissibility.
#
# decision_policy.json's D-01_ff already requires that the chosen field have parameter
# coverage for every atom type in the SMILES. Nothing enforced it: the class -> field map
# in polymer_rules.json was applied unconditionally, and an inadequate field announced
# itself only by crashing the build.
#
# This implements the policy's require clauses the way select_hardware.py implements
# D-08's -- the Planner calls it and transcribes the result rather than re-deriving it.
#
# Order of operations, and what each step is allowed to decide:
#
#   1 ADMISSIBILITY   ff_capability -- can this installation integrate the field, and can
#                     the front end type this SMILES? Hard gate; removes candidates.
#   2 PROVENANCE      ff_provenance on the cell step 1 already built -- were the emitted
#                     parameters locally invented, silently zeroed, or taken from a
#                     wildcard fallback? Demotes a candidate, never drops it.
#   3 ARCHIVE PRIOR   ff_domain -- reported only. Its own leave-one-family-out backtest
#                     finds extrapolation anti-correlated with error, so it must not rank.
#   4 CHOICE          the class default when admissible, else a DOI-backed alternative,
#                     else escalate.
#   5 SPREAD          count independent lineages among survivors. Agreement inside one
#                     lineage (pcff/pcff_ore/compass are all Class II) is not evidence.
#
# Prints JSON, always exits 0.
# ===========================================================================
LINEAGE = {
    "pcff": "class2", "pcff_ore": "class2", "compass": "class2",
    "opls/2024/opls-aa": "opls", "opls/2012/opls-aa": "opls",
    # OPLS-UA is a distinct representation (no explicit H, no improper term) fit
    # separately from OPLS-AA -- not the same functional form, so it gets its own
    # lineage bucket rather than being folded into "opls".
    "opls/2024/opls-ua": "opls_ua", "opls/2012/opls-ua": "opls_ua",
    "trappe-ua": "ua", "trappe-eh": "ua",
    "gaff": "gaff", "gaff2": "gaff", "gaff2_mod": "gaff",
    "dreiding": "dreiding", "charmm/c36a": "charmm",
}


def _provenance(field, cell_dir, emc_root):
    if not cell_dir:
        return {"verdict": "FF_PROVENANCE_NOT_CHECKED",
                "reason": "no built cell — front end does not emit an EMC parameter file"}
    try:
        return assess_provenance(cell_dir, field, emc_root)
    except Exception as e:  # noqa: BLE001 — a reader failure must not decide the field
        return {"verdict": "FF_PROVENANCE_NOT_CHECKED", "reason": f"{type(e).__name__}: {e}"}


def _archive_prior(field, cell_dir, archive_root):
    if not cell_dir:
        return {"verdict": "FF_UNAVAILABLE", "reason": "no built cell to fingerprint"}
    try:
        fp = cell_fingerprint(cell_dir)
        if fp is None:
            return {"verdict": "FF_UNAVAILABLE", "reason": "no readable emc_build.params"}
        out = assess_domain(fp, build_vocabulary(archive_root), field)
    except Exception as e:  # noqa: BLE001
        return {"verdict": "FF_UNAVAILABLE", "reason": f"{type(e).__name__}: {e}"}
    return {k: out[k] for k in ("verdict", "extrapolated_types",
                                "extrapolated_atom_fraction", "is_accuracy_prediction")
            if k in out}


def select_forcefield(polymer_class, smiles, fields=None, archive_root="manuscript/data",
                      emc_root=EMC_ROOT, keep_dir=None):
    rules = load_rules()
    cls = get_class_entry(rules, polymer_class, warn_on_miss=True)
    default = cls.get("ff_accuracy_prior")
    if not default:
        return {"error": f"polymer_rules.json class {polymer_class!r} has no ff_accuracy_prior"}

    tmp = keep_dir or tempfile.mkdtemp(prefix="ffsel_")
    cap = assess_all(smiles, fields, keep_dir=tmp)
    if "error" in cap:
        return cap

    assessed = {}
    for field, r in cap["fields"].items():
        entry = {"admissible": r["candidate"],
                 "integrates": r["integrates"],
                 "types_smiles": r["types_smiles"],
                 "typing_error": r["typing_error"] or None,
                 "lineage": LINEAGE.get(field, field)}
        if r["candidate"]:
            entry["provenance"] = _provenance(field, r.get("cell_dir"), emc_root)
            entry["archive_prior"] = _archive_prior(field, r.get("cell_dir"), archive_root)
            entry["demoted"] = (entry["provenance"].get("verdict")
                                == "FF_PROVENANCE_BLOCKING")
        assessed[field] = entry

    admissible = [f for f, e in assessed.items() if e["admissible"]]
    clean = [f for f in admissible if not assessed[f].get("demoted")]

    # 4 -- choice
    alternatives, uncertainties = [], []
    if default in clean:
        choice, confidence = default, "high"
        reason = (f"class default {default!r} is admissible for this SMILES and its "
                  "emitted parameters carry no blocking provenance flag")
    elif default in admissible:
        choice, confidence = default, "medium"
        reason = (f"class default {default!r} is admissible but its parameters carry a "
                  "blocking provenance flag — see provenance.findings; the flag must be "
                  "acknowledged in this plan's uncertainties, not silently inherited")
        uncertainties.append({"name": "ff_parameter_provenance", "dominant": False,
                              "field": default,
                              "flags": assessed[default]["provenance"].get("counts", {})})
    else:
        doi_backed = [f for f in clean if cls.get("ff_justification_doi")
                      and f != default]
        if doi_backed:
            choice, confidence = sorted(doi_backed)[0], "low"
            reason = (f"class default {default!r} is NOT admissible for this SMILES "
                      f"({assessed.get(default, {}).get('typing_error')}); fell back to "
                      f"{choice!r}, which is admissible and carries class-level DOI "
                      "evidence")
        else:
            choice, confidence = None, "none"
            reason = (f"class default {default!r} is not admissible for this SMILES and "
                      "no admissible alternative carries DOI-backed evidence — escalate "
                      "rather than guess")
        uncertainties.append({"name": "ff_transferability", "dominant": True,
                              "reduction_probe": "literature_anchor"})
    alternatives = [{"field": f, "lineage": assessed[f]["lineage"],
                     "archive_prior": assessed[f].get("archive_prior", {}).get("verdict")}
                    for f in sorted(clean) if f != choice]

    # 5 -- spread
    lineages = sorted({assessed[f]["lineage"] for f in clean})
    spread = sorted(clean) if len(lineages) >= 2 else []
    if spread:
        uncertainties.append({
            "name": "ff_cross_field_spread", "dominant": False,
            "n_lineages": len(lineages), "lineages": lineages, "candidates": spread,
            "note": "reported as an uncertainty band; it does not select a field",
        })

    return {
        "decision": {
            "id": "D-01_ff", "choice": choice,
            "criteria_evaluated": ["literature_support", "parameter_coverage",
                                   "validation_data", "computational_cost"],
            "evidence": [
                {"claim": reason},
                {"claim": f"admissible fields (integrate + type this SMILES): {admissible}"},
                {"claim": f"class prior source: polymer_rules.json:classes."
                          f"{polymer_class}.ff_accuracy_prior = {default!r}",
                 "ff_justification_doi": cls.get("ff_justification_doi"),
                 "ff_note": cls.get("ff_note")},
            ],
            "confidence": confidence,
            "alternatives": alternatives,
            # structured so validate_run_plan.py checks the choice against what was
            # measured, rather than parsing the evidence prose
            "admissible": admissible,
            "provenance_flags": (assessed.get(choice, {}).get("provenance", {})
                                 .get("counts", {}) if choice else {}),
        },
        "decided_params_override": ({} if choice == default or choice is None
                                    else {"preferred_ff": choice}),
        "uncertainties": uncertainties,
        "admissible": admissible,
        "admissible_clean": clean,
        "n_lineages": len(lineages),
        "ff_spread_candidates": spread,
        "fields": assessed,
        "note": ("Admissibility is a hard gate; provenance demotes; the archive prior is "
                 "reported and never ranks. This selects an admissible field — it does "
                 "not claim the chosen field is the most accurate one."),
    }


# ===========================================================================
# CLI
# ===========================================================================
def _cmd_select(args) -> int:
    try:
        result = select_forcefield(args.polymer_class, args.smiles,
                                   args.fields.split(",") if args.fields else None,
                                   args.archive_root, args.emc_root, args.keep_dir)
        if args.summary:
            result.pop("fields", None)
    except Exception as e:  # noqa: BLE001 — callers parse JSON, never a traceback
        result = {"error": f"{type(e).__name__}: {e}"}
    print(json.dumps(result, indent=2))
    return 0


def _cmd_capability(args) -> int:
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


def _cmd_provenance(args) -> int:
    try:
        result = assess_provenance(args.cell_dir, args.field, args.emc_root)
        if args.summary and "findings" in result:
            result = {k: v for k, v in result.items() if k != "findings"}
    except Exception as e:  # noqa: BLE001 — callers parse JSON, never a traceback
        result = {"error": f"{type(e).__name__}: {e}"}
    print(json.dumps(result, indent=2))
    return 0


def _cmd_domain(args) -> int:
    try:
        vocab = build_vocabulary(args.archive_root)
        if args.show_vocabulary:
            result = {f: {"n_types": len(d), "types": sorted(d)} for f, d in vocab.items()}
        elif not args.cell_dir or not args.field:
            result = {"error": "--cell-dir and --field are required unless --show-vocabulary"}
        else:
            fp = cell_fingerprint(args.cell_dir)
            if fp is None:
                result = {"verdict": "FF_UNAVAILABLE",
                          "reason": f"no readable emc_build.params under {args.cell_dir}"}
            else:
                result = assess_domain(fp, vocab, args.field)
                result["cell"] = {k: fp[k] for k in ("types", "n_atoms")}
    except Exception as e:  # noqa: BLE001 — callers parse JSON, never a traceback
        result = {"error": str(e)}
    print(json.dumps(result, indent=2))
    return 0


def _cmd_emc_fields(args) -> int:
    rc = 0
    try:
        m = load_manifest()
        if args.verify:
            result = verify(m, args.emc_root)
            rc = 0 if result["ok"] else 1
        elif args.apply:
            result = apply_patches(m, args.emc_root, args.dry_run)
            rc = 0 if result["ok"] else 1
        else:
            if args.patched_rows not in m["fields"]:
                result = {"error": f"unknown field {args.patched_rows!r}. "
                                   f"Known: {sorted(m['fields'])}"}
                rc = 1
            else:
                result = patched_rows(m, args.patched_rows, args.emc_root)
    except Exception as e:  # noqa: BLE001 — callers parse JSON, never a traceback
        result, rc = {"error": f"{type(e).__name__}: {e}"}, 1
    print(json.dumps(result, indent=2))
    return rc


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("select", help="D-01_ff: pick a force field for a class + SMILES")
    c.add_argument("polymer_class")
    c.add_argument("smiles")
    c.add_argument("--fields", help="comma-separated subset to consider")
    c.add_argument("--archive-root", default=os.path.join(REPO, "manuscript", "data"))
    c.add_argument("--emc-root", default=EMC_ROOT)
    c.add_argument("--keep-dir", help="retain trial cells here instead of a temp dir")
    c.add_argument("--summary", action="store_true", help="omit the per-field detail")
    c.set_defaults(func=_cmd_select)

    c = sub.add_parser("capability", help="can this field type this monomer and run here")
    c.add_argument("smiles", nargs="?", help="repeat-unit SMILES with two * connection points")
    c.add_argument("--fields", help="comma-separated subset of fields to test")
    c.add_argument("--lmp", default=LMP, help="LAMMPS binary to probe for styles")
    c.add_argument("--integration-only", action="store_true",
                   help="report style availability only, no build attempts")
    c.set_defaults(func=_cmd_capability)

    c = sub.add_parser("domain", help="is this chemistry inside the field's validated vocabulary")
    c.add_argument("--cell-dir", help="directory holding emc_build.params (+ cell.data)")
    c.add_argument("--field", help="field to assess against, e.g. pcff, compass, trappe-ua")
    c.add_argument("--archive-root", default="manuscript/data",
                   help="root of completed runs used to derive the validated vocabulary")
    c.add_argument("--show-vocabulary", action="store_true",
                   help="print the per-field validated vocabulary and exit")
    c.set_defaults(func=_cmd_domain)

    c = sub.add_parser("provenance", help="stock field rows vs local patches, per coeff")
    c.add_argument("--cell-dir", required=True, help="directory holding emc_build.params")
    c.add_argument("--field", required=True, help="e.g. pcff, opls/2024/opls-aa")
    c.add_argument("--emc-root", default=EMC_ROOT)
    c.add_argument("--summary", action="store_true", help="counts and verdict only")
    c.set_defaults(func=_cmd_provenance)

    c = sub.add_parser("emc-fields", help="verify/apply the EMC field-file patch manifest")
    g = c.add_mutually_exclusive_group(required=True)
    g.add_argument("--verify", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--patched-rows", metavar="FIELD", help="e.g. opls/2024/opls-aa")
    c.add_argument("--emc-root", default=EMC_ROOT)
    c.add_argument("--dry-run", action="store_true", help="with --apply")
    c.set_defaults(func=_cmd_emc_fields)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
