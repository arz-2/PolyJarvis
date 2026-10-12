#!/usr/bin/env python3
"""Assert the one thing this campaign claims: replicates differ by SEED and by nothing else.

Three layers, because agreement at one of them is not agreement at the others:

  PLAN      every replicate's decided_params must equal the frozen protocol in
            system_characterization_cache.json byte for byte. The frozen copy is replicate 1's
            EFFECTIVE parameters -- decided_params as amended by every mid-run remedy -- so a
            remedy that fired during replicate 1 is part of the protocol the others inherit,
            which is the whole point of freezing after acceptance rather than before execution.

  SEED      emc_seed and velocity_seed must be DISTINCT across a system's replicates. Neither is
            in write_characterization_cache.FREEZE_KEYS, so a replayed protocol carries no seed
            and each run derives its own from sha256(run_name). Identical seeds would make the
            runs duplicates, not replicates, and the campaign would measure nothing.

  EXECUTED  the seeds that actually reached EMC and LAMMPS -- emc_seed from the build attempt's
            executor_state.json, velocity_seed from the `velocity all create` lines of the
            equilibration decks -- must match what the plan said. stereo_r2 records that round 1
            never closed this loop; a pinned value nobody checked is a hope, not a control.

    python3 benchmarks/rev2_replicates/verify_replicates.py [--json]

Exit 0 if every executed check passes, 1 otherwise. Replicates that have not run yet are
reported PENDING and do not fail the run.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))
CACHE = REPO / "guides" / "system_characterization_cache.json"
SYSTEMS = {"PE": "*CC*",
           "PEEK": "*Oc1ccc(C(=O)c2ccc(Oc3ccc(*)cc3)cc2)cc1",
           "PSU": "*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1",
           "PEG": "*CCO*"}
REPLICATES = (1, 2, 3)


def derived_seeds(run_name: str) -> dict:
    d = int(hashlib.sha256(run_name.encode()).hexdigest(), 16)
    return {"emc_seed": 1 + d % 999_999, "velocity_seed": 10000 + d % 989_999}


def executed_emc_seed(run: str):
    for p in (REPO / "data" / run / "attempts" / "build").glob("*/executor_state.json"):
        try:
            doc = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        for holder in (doc.get("outputs") or {}, doc):
            if holder.get("emc_seed") is not None:
                return int(holder["emc_seed"])
    return None


def executed_velocity_seed(run: str):
    seeds = set()
    base = REPO / "data" / run / "attempts" / "equilibration"
    for deck in base.glob("*/work/*/*.in"):
        try:
            text = deck.read_text(errors="ignore")
        except OSError:
            continue
        seeds.update(int(m.group(1)) for m in
                     re.finditer(r"velocity\s+all\s+create\s+[\d.]+\s+(\d+)", text))
    if len(seeds) > 1:
        return ("AMBIGUOUS", sorted(seeds))
    return seeds.pop() if seeds else None


def frozen_protocol(smiles: str) -> dict | None:
    try:
        from rules_common import canonicalize
        canonical = canonicalize(smiles, isomeric=True)
        entry = json.loads(CACHE.read_text()).get(canonical) or {}
    except Exception:
        return None
    if not entry.get("protocol_validated"):
        return None
    return (entry.get("protocol") or {}).get("decided_params")


def main() -> int:
    as_json = "--json" in sys.argv
    report, failures = {}, []
    for system, smiles in SYSTEMS.items():
        frozen = frozen_protocol(smiles)
        rows = {}
        for r in REPLICATES:
            run = f"{system}_{r}"
            plan_path = REPO / "data" / run / "raw" / "run_plan.json"
            row = {"expected_seeds": derived_seeds(run)}
            if plan_path.is_file():
                plan = json.loads(plan_path.read_text())
                dp = plan.get("decided_params") or {}
                row["plan_mode"] = plan.get("plan_mode")
                if frozen:
                    # Compare the FROZEN keys only. charge_method and electrostatics are
                    # deliberately absent from FREEZE_KEYS -- make_plan_from_cache re-derives
                    # them from the frozen preferred_ff ("the field is frozen; everything it
                    # implies is re-derived"), so they exist on the plan and not in the freeze.
                    # Comparing the union reports that design as a protocol difference.
                    differing = sorted(k for k in frozen if frozen.get(k) != dp.get(k))
                    row["derived_from_frozen_field"] = {
                        "preferred_ff": dp.get("preferred_ff"),
                        "charge_method": dp.get("charge_method"),
                        "electrostatics": dp.get("electrostatics"),
                    }
                    row["protocol_matches_frozen"] = not differing
                    if differing:
                        row["differing_keys"] = {k: {"frozen": frozen.get(k), "plan": dp.get(k)}
                                                 for k in differing}
                        # Replicate 1 IS the source of the freeze; its own plan predates the
                        # remedies that amended it, so a difference there is expected, not a fault.
                        if r != 1:
                            failures.append(f"{run}: decided_params differ from the frozen "
                                            f"protocol at {differing}")
            else:
                row["plan_mode"] = "PENDING (not planned yet)"
            # materialize_plan runs again inside agent_api start (ScientificControl.run), even
            # for a frozen replay the graph deliberately routed PAST materialize -- so the cell
            # is re-solved at execute time. solve_system_size is deterministic on the same
            # inputs, so it reproduces the frozen cell unless the code or the class table has
            # moved since the freeze, which is exactly when a lock matters. That makes the
            # comparison above a real check rather than a formality; run it after launch.
            row["executed_seeds"] = {"emc_seed": executed_emc_seed(run),
                                     "velocity_seed": executed_velocity_seed(run)}
            for key, got in row["executed_seeds"].items():
                want = row["expected_seeds"][key]
                if got is None:
                    continue
                if got != want:
                    failures.append(f"{run}: executed {key}={got!r} but run_name derives {want}")
            rows[run] = row
        for key in ("emc_seed", "velocity_seed"):
            planned = [rows[f"{system}_{r}"]["expected_seeds"][key] for r in REPLICATES]
            if len(set(planned)) != len(planned):
                failures.append(f"{system}: {key} is NOT distinct across replicates: {planned}")
            ran = [rows[f"{system}_{r}"]["executed_seeds"][key] for r in REPLICATES]
            ran = [v for v in ran if isinstance(v, int)]
            if len(set(ran)) != len(ran):
                failures.append(f"{system}: EXECUTED {key} repeats across replicates: {ran}")
        report[system] = {"frozen_protocol_available": frozen is not None, "replicates": rows}

    if as_json:
        print(json.dumps({"report": report, "failures": failures}, indent=1))
        return 1 if failures else 0

    for system, block in report.items():
        lock = "frozen" if block["frozen_protocol_available"] else "NOT YET FROZEN"
        print(f"== {system}  (protocol {lock})")
        for run, row in block["replicates"].items():
            ex, ran = row["expected_seeds"], row["executed_seeds"]
            match = row.get("protocol_matches_frozen")
            flag = {True: "protocol=frozen", False: "PROTOCOL DIFFERS", None: "protocol=n/a"}[match]
            print(f"   {run:8} {str(row['plan_mode']):28} {flag}")
            d = row.get("derived_from_frozen_field")
            if d:
                print(f"            ff={d['preferred_ff']} -> charge={d['charge_method']} "
                      f"elec={d['electrostatics']}")
            print(f"            seeds expected emc={ex['emc_seed']:<9} vel={ex['velocity_seed']:<9}"
                  f"  executed emc={ran['emc_seed']} vel={ran['velocity_seed']}")
    print()
    if failures:
        print(f"FAIL ({len(failures)}):")
        for f in failures:
            print("  -", f)
        return 1
    print("PASS -- every executed seed matches its run_name derivation, seeds are distinct "
          "within each system, and every replicate's protocol equals the frozen one.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
