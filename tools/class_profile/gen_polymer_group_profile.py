#!/usr/bin/env python3
"""Regenerate guides/polymer_group_profile.json from RadonPy's own source.

RUNS IN THE mol-builder CONDA ENV (RadonPy must be importable). The file it writes is a
MIRROR of poly.polyinfo_classifier -- its SMARTS literals, the class->pattern binding, and
the priority ladder -- kept on disk only so rdkit_cli's `classify` can LOCATE which group
families a repeat unit contains and whether each sits on the backbone. It is never used to
assign polymer_class; that label comes from calling polyinfo_classifier itself, because
this repo's classification ground truth is that function's own behaviour and a competing
SMARTS table would drift away from it.

Print the derivation instead of writing it with --stdout; that is how
tests/test_polymer_group_profile_mirrors_radonpy.py checks the on-disk copy without needing
RadonPy in the test interpreter.

    python3 tools/class_profile/gen_polymer_group_profile.py --repo-root . [--stdout]
"""
import argparse
import ast
import inspect
import json
import sys
import textwrap
from pathlib import Path


def derive_groups() -> dict:
    """SMARTS, class->pattern binding and priority ladder, read out of the function's AST.

    Parsed rather than imported-and-introspected because the SMARTS live in local variables
    that never escape polyinfo_classifier's frame.
    """
    from radonpy.core import poly

    fn = ast.parse(textwrap.dedent(inspect.getsource(poly.polyinfo_classifier))).body[0]

    smarts = {}
    for node in fn.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            try:
                value = ast.literal_eval(node.value)
            except Exception:
                continue
            if isinstance(value, list) and value and all(isinstance(x, str) for x in value):
                smarts[node.targets[0].id] = value

    class_to_var = {}
    flag_dict = next(n.value for n in ast.walk(fn)
                     if isinstance(n, ast.Assign) and len(n.targets) == 1
                     and isinstance(n.targets[0], ast.Name) and n.targets[0].id == "flag"
                     and isinstance(n.value, ast.Dict))
    for key, value in zip(flag_dict.keys, flag_dict.values):
        var = None
        for sub in ast.walk(value):
            if isinstance(sub, ast.comprehension) and isinstance(sub.iter, ast.Name):
                var = sub.iter.id
        class_to_var[ast.literal_eval(key)] = var

    # Tier-2 families are assigned outside the dict literal: flag['PSTR'] = [...]
    for node in ast.walk(fn):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Subscript)):
            target = node.targets[0]
            if isinstance(target.value, ast.Name) and target.value.id == "flag":
                try:
                    cls = ast.literal_eval(target.slice)
                except Exception:
                    continue
                for sub in ast.walk(node.value):
                    if isinstance(sub, ast.comprehension) and isinstance(sub.iter, ast.Name):
                        class_to_var[cls] = sub.iter.id

    order = []

    def walk_chain(stmts):
        """The terminal if/elif ladder IS the priority order; rank is its position."""
        for st in stmts:
            if not isinstance(st, ast.If):
                continue
            test = st.test
            if (isinstance(test, ast.Subscript) and isinstance(test.value, ast.Name)
                    and test.value.id == "flag"):
                cls = ast.literal_eval(test.slice)
                for b in st.body:
                    if (isinstance(b, ast.Assign) and isinstance(b.targets[0], ast.Name)
                            and b.targets[0].id == "class_id"):
                        order.append((cls, ast.literal_eval(b.value)))
            walk_chain(st.orelse)

    walk_chain(fn.body)

    groups = {}
    for rank, (cls, class_id) in enumerate(order, start=1):
        var = class_to_var.get(cls)
        groups[cls] = {
            "class_id": class_id,
            "priority_rank": rank,
            "smarts_var": var,
            "smarts": smarts.get(var) if var else None,
            "tier": 1 if var in smarts and cls not in ("PSTR", "PACR") else
                    (2 if var else "element_count"),
        }
    return groups


def build_document() -> dict:
    return {
        "_metadata": {
            "description": (
                "RadonPy's own PoLyInfo class SMARTS and priority order, mirrored for ONE "
                "purpose: locating which functional groups a repeat unit contains and where. "
                "It is NEVER used to assign polymer_class -- that label comes from calling "
                "poly.polyinfo_classifier directly. Keeping a second taxonomy here is exactly "
                "what this file must not become."
            ),
            "mirrors": {
                "file": "radonpy/core/poly.py",
                "function": "polyinfo_classifier",
                "regenerate": "tools/class_profile/gen_polymer_group_profile.py (mol-builder env)",
                "verified_by": "tests/test_polymer_group_profile_mirrors_radonpy.py",
            },
            "tiers": {
                "1": "matched on extract_mainchain -> make_cyclicpolymer(n=4); backbone-only by construction",
                "2": "styrene/acryl, matched with the [14C] mainchain isotope tagging polyinfo_classifier applies to its own working copy",
                "element_count": "no SMARTS; RadonPy decides these by element/bond counting",
            },
        },
        "groups": derive_groups(),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--repo-root", default=".")
    p.add_argument("--stdout", action="store_true",
                   help="print the derivation instead of writing it (used by the mirror test)")
    args = p.parse_args()

    doc = build_document()
    if args.stdout:
        print(json.dumps(doc, indent=2))
        return 0
    out = Path(args.repo_root) / "guides" / "polymer_group_profile.json"
    out.write_text(json.dumps(doc, indent=2) + "\n")
    print(json.dumps({"status": "written", "path": str(out), "n_groups": len(doc["groups"])}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
