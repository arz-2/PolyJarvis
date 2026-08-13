#!/usr/bin/env python3
"""Is this polymer inside a force field's demonstrated domain?

A classical force field's accuracy lives in its per-atom-type parameters, so the
question that can be answered without experimental data is not "is this field
correct" but "has this field already been validated on the types this molecule is
built from".

Measured on the archive, PCFF's validated vocabulary is 15 types across 7 families,
and the overlap is high -- PEG, PMMA and PS introduce no type the others do not
already cover; PEEK, PLA, PSU and PVC add one or two each.

THIS IS A PROVENANCE SIGNAL, NOT AN ACCURACY PREDICTOR. It answers "has this field
been exercised on this chemistry in a completed run here", which is a fact about
what a prior is worth, not a forecast of error. Backtested leave-one-family-out
against measured error on this archive, extrapolation does NOT predict inaccuracy:

    corr(extrapolated atom fraction, |K error|)       = -0.26
    corr(extrapolated atom fraction, |density error|) = -0.64   (n=6)

Both are negative -- more extrapolation went with *better* agreement, largely
because TraPPE-UA's small validated vocabulary makes its two accurate families look
maximally extrapolating. The counter-examples are direct: PLA extrapolates on 0.2%
of its atoms and has the archive's worst K error (+33%); cis-PBD extrapolates on
49.8% and has among its best densities (-0.2%).

So: report this verdict, never gate on it. Using it to discard a candidate field
would have thrown out TraPPE-UA for cis-PBD -- the most accurate density in the
whole archive. Accuracy has to be decided by the reference-free comparators and the
cross-field spread, not here.

Runs at build time, before any long simulation. Prints JSON, always exits 0 --
callers transcribe the verdict rather than re-deriving it.
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

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


def assess(fingerprint, vocabulary, field):
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


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cell-dir", help="directory holding emc_build.params (+ cell.data)")
    p.add_argument("--field", help="field to assess against, e.g. pcff, compass, trappe-ua")
    p.add_argument("--archive-root", default="manuscript/data",
                   help="root of completed runs used to derive the validated vocabulary")
    p.add_argument("--show-vocabulary", action="store_true",
                   help="print the per-field validated vocabulary and exit")
    args = p.parse_args()

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
                result = assess(fp, vocab, args.field)
                result["cell"] = {k: fp[k] for k in ("types", "n_atoms")}
    except Exception as e:  # noqa: BLE001 — callers parse JSON, never a traceback
        result = {"error": str(e)}

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
