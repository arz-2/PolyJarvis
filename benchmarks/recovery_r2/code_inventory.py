#!/usr/bin/env python3
"""Which Finding codes can actually be minted -- the design surface for a fault catalog.

`default_remedies()` routes 42 codes; 15 of them no producer names, so a fault designed
around one would never fire and the leg would silently measure nothing. The unreachable set
is not re-derived here: tests/test_recovery_code_inventory.py already owns it and fails when
it drifts, so this reads that map rather than keeping a second copy that can rot.

    python3 benchmarks/recovery_r2/code_inventory.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "tests"))

from workflow_engine import default_remedies  # noqa: E402
from test_recovery_code_inventory import UNREACHABLE  # noqa: E402


def inventory() -> dict:
    live_auto, live_agent, dead = {}, {}, {}
    for remedy in default_remedies():
        for code in sorted(remedy.codes):
            row = {"remedy_id": remedy.remedy_id, "local_cap": remedy.local_cap,
                   "invalidate_from": remedy.invalidate_from}
            if code in UNREACHABLE:
                dead[code] = {**row, "why": UNREACHABLE[code]}
            elif remedy.agent_only:
                live_agent[code] = row
            else:
                live_auto[code] = row
    return {"live_automatic": live_auto, "live_agent_only": live_agent, "unreachable": dead}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    inv = inventory()
    if args.json:
        print(json.dumps(inv, indent=2))
        return 0
    total = sum(len(v) for v in inv.values())
    print(f"{total} routed codes: {len(inv['live_automatic'])} live automatic, "
          f"{len(inv['live_agent_only'])} live agent-only, {len(inv['unreachable'])} unreachable\n")
    for title, key in (("LIVE -- automatic ladder", "live_automatic"),
                       ("LIVE -- agent_only (escalates, 2-call cap)", "live_agent_only"),
                       ("UNREACHABLE -- do not design a fault around these", "unreachable")):
        print(title)
        for code, row in sorted(inv[key].items()):
            extra = f"  [{row['why']}]" if "why" in row else \
                    f"  cap={row['local_cap']} invalidate_from={row['invalidate_from']}"
            print(f"  {code:38s} -> {row['remedy_id']}{extra}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
