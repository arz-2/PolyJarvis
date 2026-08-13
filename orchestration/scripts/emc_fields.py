#!/usr/bin/env python3
"""Local modifications to the installed EMC field tree.

EMC's field files live outside this repo (~/emc/field) and have been hand-edited.
An edit there changes what a polymer is built from with no git diff, and a reinstall
silently reverts it. emc_fields/ holds the vendor baseline, the diffs, and the hashes
of both states; this script is the only thing that reads them.

  --verify        installed tree matches the manifest        (exit 1 on mismatch)
  --apply         re-apply the patches to a fresh install
  --patched-rows  parameter rows this installation added or changed, by section
                  — the input ff_provenance.py uses to tell a locally authored
                  parameter from a vendor one

Prints JSON.
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST = os.path.join(REPO, "emc_fields", "manifest.json")
EMC_ROOT = os.environ.get("EMC_ROOT", os.path.expanduser("~/emc"))

# leading columns that name atom types, per .prm section. A row's remaining columns
# are its parameters.
_ARITY = {"INCREMENT": 2, "NONBOND": 1, "BOND": 2, "ANGLE": 3, "ANGLE_AUTO": 3,
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
                        n = _ARITY.get(section)
                        if n:
                            result["sections"].setdefault(section, []).append(t[:n])
        except OSError:
            continue
    result["typing_rules"] = sorted(set(result["typing_rules"]))
    result["n_rows"] = sum(len(v) for v in result["sections"].values())
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--verify", action="store_true")
    g.add_argument("--apply", action="store_true")
    g.add_argument("--patched-rows", metavar="FIELD",
                   help="e.g. opls/2024/opls-aa")
    p.add_argument("--emc-root", default=EMC_ROOT)
    p.add_argument("--dry-run", action="store_true", help="with --apply")
    args = p.parse_args()

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


if __name__ == "__main__":
    sys.exit(main())
