#!/usr/bin/env python3
"""Measure EMC force-field coverage over RadonPy's PI1070, lever by lever.

The question this answers is not "does the class default work" -- docs/ff_capability_gaps.json
already sampled that at 71/109 -- but "how much of the real chemical space becomes buildable,
and by WHICH lever", so a routing decision can be made from numbers instead of from one
member's anecdote.

Four arms, each with its own denominator:

  arm0  class-preferred field, SMILES as given            the baseline, and the failure buckets
  arm1  every registered EMC field                        would a per-SMILES cascade help?
  arm2  mechanically re-cut repeat unit, class field      does the POXI fix generalize?
  arm3  arm1 union arm2                                   the reachable ceiling

Arms 1-3 run only on arm0's failures, so the sweep costs roughly one full pass plus a few
partial ones.

Why this does not call forcefield.check_typing: that helper keeps only the last three lines
of EMC's output, and the diagnostic this sweep exists to collect -- the per-pair
"increment pair {X, Y} not found" warnings -- is printed BEFORE the abort line. The bucketing
is the deliverable, so the probe here keeps the whole transcript and throws the cell away.

Results stream to JSONL so a killed sweep resumes instead of restarting.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

EMC_BUILDER = str(REPO_ROOT / "mcp-servers" / "mcp-emc-server" / "smiles_to_emc.py")
PI1070 = Path.home() / "RadonPy" / "data" / "PI1070.csv"

# mcp-servers/mcp-mol-builder-server/server.py:POLYINFO_CLASS_NAMES -- PI1070's
# polymer_class column carries the integer id, this repo keys everything by the code.
CLASS_BY_ID = {
    1: "PHYC", 2: "PSTR", 3: "PVNL", 4: "PACR", 5: "PHAL", 6: "PDIE", 7: "POXI",
    8: "PSUL", 9: "PEST", 10: "PAMD", 11: "PURT", 12: "PURA", 13: "PIMD", 14: "PANH",
    15: "PCBN", 16: "PIMN", 17: "PSIL", 18: "PPHS", 19: "PKTN", 20: "PSFO", 21: "PPNL",
}

# dp/nchains are deliberately tiny: typing is what is under test, not packing, and a
# typing failure surfaces on the first repeat unit. Matches forcefield._try_emc.
PROBE_DP, PROBE_NCHAINS = 4, 2


# ─── probe ────────────────────────────────────────────────────────────────────────────

def probe(smiles: str, field: str, timeout: int = 300) -> dict:
    """Run one real EMC trial build. Returns {built, bucket, detail, missing_pairs}."""
    workdir = tempfile.mkdtemp(prefix="ffsweep_")
    try:
        r = subprocess.run(
            [sys.executable, EMC_BUILDER, smiles, workdir, "--field", field,
             "--dp", str(PROBE_DP), "--nchains", str(PROBE_NCHAINS)],
            capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "") + (r.stderr or "")
        built = r.returncode == 0
    except subprocess.TimeoutExpired:
        return {"built": False, "bucket": "timeout", "detail": f"exceeded {timeout}s",
                "missing_pairs": []}
    except (OSError, subprocess.SubprocessError) as e:
        return {"built": False, "bucket": "harness_error",
                "detail": f"{type(e).__name__}: {e}", "missing_pairs": []}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    pairs = sorted(set(re.findall(r"increment pair \{([^}]+)\} not found", out)))
    torsions = sorted(set(re.findall(r"no torsion coefficients found for \[([^\]]+)\]", out)))
    if built:
        # EMC exits 0 even when it substituted a zero for a row it could not find, so a
        # clean exit with warnings is NOT a clean build -- that is the whole reason
        # do_build now runs a provenance check.
        return {"built": True,
                "bucket": "built_with_substitutions" if (pairs or torsions) else "built_clean",
                "detail": "", "missing_pairs": pairs + torsions}

    if "Missing rules" in out:
        bucket = "missing_typing_rule"       # no template types this atom at all
    elif torsions:
        bucket = "missing_torsion_row"       # typed fine, parameter row absent
    elif pairs:
        bucket = "missing_increment_row"     # typed fine, charge increment absent
    elif "Missing force field parameters" in out:
        bucket = "missing_parameters_unattributed"
    elif r.returncode < 0:
        bucket = f"segfault_signal_{-r.returncode}"
    else:
        bucket = "other"
    tail = " | ".join(out.strip().splitlines()[-3:])[:400]
    return {"built": False, "bucket": bucket, "detail": tail,
            "missing_pairs": pairs + torsions}


# ─── population ───────────────────────────────────────────────────────────────────────

def load_population(rules: dict, limit: int | None = None, classes: set | None = None) -> list:
    """PI1070 rows that are EMC-routed, with their class code and preferred field attached.

    RadonPy-routed classes (PAMD/PCBN/PURA) are excluded rather than counted as failures:
    they are not asking the EMC question, and folding them in would understate EMC coverage
    against the space EMC is actually responsible for.
    """
    rows = []
    with open(PI1070) as fh:
        for r in csv.DictReader(fh):
            code = CLASS_BY_ID.get(int(r["polymer_class"]))
            entry = rules["classes"].get(code) if code else None
            if not entry or entry.get("preferred_builder") != "emc":
                continue
            if classes and code not in classes:
                continue
            rows.append({"monomer_id": r["monomer_ID"], "smiles": r["smiles"],
                         "polymer_class": code, "field": entry["preferred_ff"]})
            if limit and len(rows) >= limit:
                break
    return rows


def emc_fields() -> list:
    """Every registered EMC-front-end field, class defaults first so a cascade result reads
    as 'the default plus what else was tried'."""
    from forcefield import FIELDS
    # charmm/c36a is registered so its limitation is re-measured rather than assumed, but it
    # cannot type a SMILES at all -- confirmed here on polyethylene, the simplest possible
    # case, which fails with "Missing rules". Running it against every cascade candidate
    # would spend ~15 min producing a column of known negatives.
    cannot_type = {"charmm/c36a"}
    defaults = ["pcff", "opls/2024/opls-aa", "trappe-ua"]
    rest = sorted(k for k, v in FIELDS.items()
                  if v["front_end"] == "emc" and k not in defaults and k not in cannot_type)
    return defaults + rest


# ─── arms ─────────────────────────────────────────────────────────────────────────────

def run_arm(name: str, jobs: list, out_path: Path, resume: bool = True) -> list:
    """jobs = [{key, smiles, field, ...}]. Streams one JSON line per probe."""
    done = {}
    if resume and out_path.exists():
        for line in out_path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                done[rec["key"]] = rec
    todo = [j for j in jobs if j["key"] not in done]
    print(f"[{name}] {len(done)} cached, {len(todo)} to run", flush=True)
    t0 = time.time()
    with out_path.open("a") as fh:
        for i, job in enumerate(todo, 1):
            rec = {**job, **probe(job["smiles"], job["field"])}
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            done[job["key"]] = rec
            if i % 25 == 0 or i == len(todo):
                rate = (time.time() - t0) / i
                print(f"[{name}] {i}/{len(todo)}  {rate:.1f}s/probe  "
                      f"eta {rate * (len(todo) - i) / 60:.0f}min", flush=True)
    return list(done.values())


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out-dir", default=str(REPO_ROOT / "docs" / "ff_coverage_sweep"))
    p.add_argument("--limit", type=int, default=None, help="first N of the population")
    p.add_argument("--classes", default=None, help="comma-separated class codes")
    p.add_argument("--arms", default="0,1,2", help="which arms to run")
    args = p.parse_args()

    from rules_common import load_rules
    rules = load_rules()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    arms = {a.strip() for a in args.arms.split(",")}
    classes = {c.strip().upper() for c in args.classes.split(",")} if args.classes else None

    pop = load_population(rules, args.limit, classes)
    print(f"population: {len(pop)} EMC-routed PI1070 polymers", flush=True)

    # arm0 is always loaded, even when not selected: arms 1 and 2 are defined on its
    # failures, so running "--arms 1" against an empty baseline would silently do nothing.
    arm0_path = out_dir / "arm0.jsonl"
    jobs0 = [{**r, "key": f"{r['monomer_id']}|{r['field']}|asgiven"} for r in pop]
    if "0" in arms:
        arm0 = run_arm("arm0", jobs0, arm0_path)
    elif arm0_path.exists():
        keys = {j["key"] for j in jobs0}
        arm0 = [json.loads(l) for l in arm0_path.read_text().splitlines() if l.strip()]
        arm0 = [r for r in arm0 if r["key"] in keys]
    else:
        sys.exit("arms 1/2 need arm0 results; run --arms 0 first")

    by_id = {r["monomer_id"]: r for r in arm0}
    failed = [r for r in arm0 if not r["built"]]
    print(f"arm0: {len(arm0) - len(failed)}/{len(arm0)} built "
          f"({100 * (len(arm0) - len(failed)) / max(len(arm0), 1):.0f}%)", flush=True)

    if "1" in arms and failed:
        fields = emc_fields()
        jobs = [{"monomer_id": r["monomer_id"], "smiles": r["smiles"],
                 "polymer_class": r["polymer_class"], "field": f,
                 "key": f"{r['monomer_id']}|{f}|asgiven"}
                for r in failed for f in fields if f != r["field"]]
        run_arm("arm1", jobs, out_dir / "arm1.jsonl")

    if "2" in arms and failed:
        from recut import recut_candidates
        jobs = []
        for r in failed:
            for n, alt in enumerate(recut_candidates(r["smiles"])):
                jobs.append({"monomer_id": r["monomer_id"], "smiles": alt,
                             "original_smiles": r["smiles"],
                             "polymer_class": r["polymer_class"],
                             "field": by_id[r["monomer_id"]]["field"],
                             "key": f"{r['monomer_id']}|{by_id[r['monomer_id']]['field']}|recut{n}"})
        run_arm("arm2", jobs, out_dir / "arm2.jsonl")

    print("done", flush=True)


if __name__ == "__main__":
    sys.exit(main())
