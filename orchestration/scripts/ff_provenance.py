#!/usr/bin/env python3
"""Where did this cell's force-field parameters actually come from?

A field that types a molecule can still be wrong for it, because the numbers it used
were not fitted for this chemistry. EMC never says so: it writes a parameter file and
exits 0 whether a row came from the published field, from a wildcard fallback, from a
local hand-edit, or from a silent zero substituted for a row that does not exist.

This reads a built cell's emc_build.params -- every emitted `*_coeff` row carries its
type tuple as a trailing comment -- and resolves each tuple back against the installed
field file:

  LOCAL_PATCH       the row was added or changed on this machine (emc_fields.py)
  ZERO_SUBSTITUTED  all-zero parameters AND no source row -- EMC filled in a zero
  AUTO_FALLBACK     matched only a wildcard/_auto section, not a specific row
  NO_SOURCE_ROW     nonzero parameters no source row explains -- a lookup bug here,
                    not a defect in the field; this flag is the parser's self-test

SCOPE: this checks whether a source row EXISTS, not whether the emitted number equals
it. Reproducing EMC's values means reproducing its unit conversions and Class II
cross-term arithmetic, which would trade a reliable existence check for an unreliable
equality one. A wrong-but-present parameter is out of scope and stays out.

Prints JSON, always exits 0 -- callers transcribe the verdict.
"""
import argparse
import fnmatch
import itertools
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import emc_fields  # noqa: E402
import ff_capability  # noqa: E402

EMC_ROOT = os.environ.get("EMC_ROOT", os.path.expanduser("~/emc"))

# `# <Name> Coeffs` section header -> interaction kind. A Class II deck reuses the same
# `*_coeff` keyword for its cross terms (BondBond, EndBondTorsion, AngleAngle, ...),
# distinguishing them by a sub-tag in column 2, so the section header is the only
# reliable discriminator. Cross terms are reported as unchecked rather than silently
# dropped -- each has its own .frc section and tuple convention, and a half-right check
# would be worse than none.
_KINDS = {"Pair": "pair", "Bond": "bond", "Angle": "angle",
          "Dihedral": "torsion", "Improper": "improper"}
_ARITY = {"pair": 1, "bond": 2, "angle": 3, "torsion": 4, "improper": 4}

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
        n = _ARITY[kind]
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
        n = _ARITY[kind]
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
    field = ff_capability.FIELDS.get(field, {}).get("name", field)
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
        m = emc_fields.load_manifest()
        if field not in m["fields"]:
            return set(), []
        pr = emc_fields.patched_rows(m, field, emc_root)
    except Exception:  # noqa: BLE001 — absent manifest must not fail the whole check
        return set(), []
    kind_of = {"BOND": "bond", "ANGLE": "angle", "TORSION": "torsion",
               "IMPROPER": "improper", "NONBOND": "pair"}
    rows = {(kind_of[s], tuple(t)) for s, ts in pr["sections"].items()
            if s in kind_of for t in ts}
    rows |= {(k, tuple(reversed(t))) for k, t in rows}
    return rows, pr["sections"].get("INCREMENT", [])


def assess(cell_dir, field, emc_root=EMC_ROOT):
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


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cell-dir", required=True, help="directory holding emc_build.params")
    p.add_argument("--field", required=True, help="e.g. pcff, opls/2024/opls-aa")
    p.add_argument("--emc-root", default=EMC_ROOT)
    p.add_argument("--summary", action="store_true", help="counts and verdict only")
    args = p.parse_args()

    try:
        result = assess(args.cell_dir, args.field, args.emc_root)
        if args.summary and "findings" in result:
            result = {k: v for k, v in result.items() if k != "findings"}
    except Exception as e:  # noqa: BLE001 — callers parse JSON, never a traceback
        result = {"error": f"{type(e).__name__}: {e}"}

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
