#!/usr/bin/env python3
"""
DEPRECATED 2026-09-01 -- one cell build per run. Do not use; kept for provenance only.

Retired by decision, and the decision closed an inconsistency: this splitter sized its
bulk_modulus arm from property_floors()'s entanglement_bm floor, which select_system_size.py
deliberately EXCLUDES from the binding size (:262-277, user-directed 2026-08-25) on the grounds
that entanglement Me gates the plateau shear modulus, not an EOS/local-packing quantity like K.
So it built a second, larger, more expensive cell on a criterion the size selector had already
been changed to stop honouring.

select_system_size() already produces the single cell this replaces: property_floors() collapsed
via max() over the requested properties. Nothing in the plan -> execute path ever called this
script or merge_arm_summaries.py -- both were opt-in and manually invoked -- so retiring them
changes no automated behaviour.

ORIGINAL DOCSTRING FOLLOWS

merge_arm_summaries.py — combine two arms' run_summary.json (from
plan_system_size_arms.py's split) into one report.

generate_run_summary.py (mcp-servers/mcp-lammps-engine/analysis_scripts/) and its caller
run_campaign.py:do_summary both hard-assume one output_dir / one DP / one .data lineage
per summary -- there is no code path that combines two runs' results, so this is new,
not a change to that schema. It only reads two already-produced run_summary.json files
and unions them; it never re-derives or re-computes a result.

Never guesses which arm's value wins: refuses (raises, does not silently pick one) when
the two arms disagree on which molecule they are (smiles/polymer_class mismatch -- these
must be two arms of the SAME split, not two unrelated runs), when the same results/
artifacts key holds different non-null values in both arms, or when a property named via
--expect is absent from both.

Usage:
  python3 orchestration/scripts/merge_arm_summaries.py \\
      --a data/PMMA1_tg --b data/PMMA1_bm --out data/PMMA1/run_summary.json \\
      [--expect tg,density,bulk_modulus]
  --a/--b accept either a run_name (resolved via workflow_state.json's
  stages.summary.accepted_attempt, the same convention run_campaign.py itself uses) or a
  direct path to a run_summary.json file.
Prints the merged JSON to stdout in addition to writing --out. Exits 1 with
{"error": ...} on a refusal (never exits 0 with a silently-resolved conflict).
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _resolve_summary_path(ref: str) -> Path:
    """`ref` is either a path to a run_summary.json or a bare run_name."""
    p = Path(ref)
    if p.suffix == ".json":
        return p
    run_dir = REPO_ROOT / "data" / ref
    state = json.loads((run_dir / "workflow_state.json").read_text())
    accepted = state.get("stages", {}).get("summary", {}).get("accepted_attempt")
    if not accepted:
        raise ValueError(f"run {ref!r} has no accepted summary attempt in workflow_state.json")
    return run_dir / "attempts" / "summary" / accepted / "raw" / "run_summary.json"


def _union_dict(key: str, a: dict, b: dict) -> dict:
    """Union two dicts key-by-key, refusing on a conflicting non-null duplicate."""
    out = dict(a)
    for k, v in b.items():
        if k in out and out[k] not in (None, {}, []) and v not in (None, {}, []) and out[k] != v:
            raise ValueError(f"{key}.{k} disagrees between arms: {out[k]!r} vs {v!r} -- "
                             "refusing to guess which arm is authoritative")
        if k not in out or out[k] in (None, {}, []):
            out[k] = v
    return out


# run fields that are intrinsically per-arm (a different DP/nchain/name/atom-count/
# timestamp per arm) -- merging these into one value would misattribute a result to the
# wrong system size (e.g. a K measured at DP=125 reported under run.dp=20 from the tg
# arm). They are nulled in the merged "run" block; the real per-arm values live in "arms".
_ARM_SPECIFIC_RUN_FIELDS = {"name", "dp", "n_chains", "n_atoms", "date_start", "date_end"}


def merge_summaries(a: dict, b: dict, expect=None) -> dict:
    run_a, run_b = a.get("run", {}), b.get("run", {})
    for field in ("smiles", "polymer_class"):
        va, vb = run_a.get(field), run_b.get(field)
        if va and vb and va != vb:
            raise ValueError(f"arms disagree on run.{field}: {va!r} vs {vb!r} -- these are "
                             "not two arms of the same split")

    results = _union_dict("results", a.get("results", {}), b.get("results", {}))
    if expect:
        missing = sorted(p for p in expect if p not in results or results[p] is None)
        if missing:
            raise ValueError(f"expected propert{'y' if len(missing)==1 else 'ies'} "
                             f"{missing} missing from both arms' results")

    # D-04_system_size is EXPECTED to disagree between arms -- that divergence is the
    # entire reason a two-arm split exists. Every other decision (D-01_ff, D-05_convergence,
    # ...) should genuinely agree, since both arms are the same molecule/class, so those
    # still go through the strict conflict check.
    decisions_a, decisions_b = dict(a.get("decisions", {})), dict(b.get("decisions", {}))
    d04_a = decisions_a.pop("D-04_system_size", None)
    d04_b = decisions_b.pop("D-04_system_size", None)
    decisions = _union_dict("decisions", decisions_a, decisions_b)
    if d04_a or d04_b:
        decisions["D-04_system_size"] = {"a": d04_a, "b": d04_b}

    shared_run_a = {k: v for k, v in run_a.items() if k not in _ARM_SPECIFIC_RUN_FIELDS}
    shared_run_b = {k: v for k, v in run_b.items() if k not in _ARM_SPECIFIC_RUN_FIELDS}
    run = _union_dict("run", shared_run_a, shared_run_b)
    run.update({f: None for f in _ARM_SPECIFIC_RUN_FIELDS})

    merged = {
        "run": run,
        "decisions": decisions,
        "plan": None,
        "results": results,
        "convergence": _union_dict("convergence", a.get("convergence", {}), b.get("convergence", {})),
        "structural_checks": _union_dict("structural_checks", a.get("structural_checks", {}),
                                         b.get("structural_checks", {})),
        "artifacts": _union_dict("artifacts", a.get("artifacts", {}), b.get("artifacts", {})),
        "artifacts_missing": a.get("artifacts_missing", []) + b.get("artifacts_missing", []),
        "provenance": _union_dict("provenance", a.get("provenance", {}), b.get("provenance", {})),
        "arms": {
            "a": {"run_name": run_a.get("name"), "dp": run_a.get("dp"),
                 "n_chains": run_a.get("n_chains")},
            "b": {"run_name": run_b.get("name"), "dp": run_b.get("dp"),
                 "n_chains": run_b.get("n_chains")},
        },
    }
    return merged


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--a", required=True, help="run_name or run_summary.json path, arm A")
    p.add_argument("--b", required=True, help="run_name or run_summary.json path, arm B")
    p.add_argument("--out", required=True, help="path to write the merged run_summary.json")
    p.add_argument("--expect", default=None,
                   help="comma-separated property names that must appear in the merge")
    args = p.parse_args()

    try:
        a = json.loads(_resolve_summary_path(args.a).read_text())
        b = json.loads(_resolve_summary_path(args.b).read_text())
        expect = set(args.expect.split(",")) if args.expect else None
        merged = merge_summaries(a, b, expect=expect)
    except Exception as e:  # noqa: BLE001 -- callers parse JSON, never a traceback
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}, indent=2))
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, indent=2))
    print(json.dumps(merged, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
