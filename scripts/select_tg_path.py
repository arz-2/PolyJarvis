#!/usr/bin/env python3
"""Select the Tg-summary path for run-summary, by the multirate slope-gate verdict.

Replaces the inline shell the orchestrator used to hand-execute in CLAUDE.md Phase C
(deriving TG_PATH by hand was the PLA3 footgun — feedback_run_summary_tg_mismatch.md).

Convention:
  slope_gate_pass=True  -> slowest rate (tg_rates[0]) — the trusted DSC-convention point
  slope_gate_pass=False -> the class fallback rate from decided_params.tg_slope_gate_fallback:
    "highest_rate" (default) — least glassy-contaminated fallback
    "slowest_rate" (rigid aromatics PKTN/PSFO) — most-equilibrated; fast rates cold-start
    from the 300 K glass and invert the Tg-vs-rate trend

Inputs:
  --plan       run_plan.json            (authoritative tg_rates_K_per_ns)
  --multirate  tg_multirate_result.json (slope_gate_pass; its dir is the run's raw/ dir)

Prints two eval-able lines to stdout:
  TG_PATH=<raw_dir>/tg_r<rate>/tg_summary.json
  SLOPE_GATE=<true|false>
"""
import argparse
import json
import os
import sys


def _fmt_rate(rate):
    """Match the jq/dir-naming convention: integer-valued rates have no decimal (tg_r40)."""
    f = float(rate)
    return str(int(f)) if f == int(f) else str(f)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True,
                    help="run_plan.json — source of decided_params.tg_rates_K_per_ns")
    ap.add_argument("--multirate", required=True,
                    help="tg_multirate_result.json — source of slope_gate_pass; its dir is raw/")
    args = ap.parse_args()

    with open(args.plan) as fh:
        plan = json.load(fh)
    with open(args.multirate) as fh:
        multi = json.load(fh)

    rates = plan.get("decided_params", {}).get("tg_rates_K_per_ns")
    if not rates:
        sys.exit("ERROR: plan has no decided_params.tg_rates_K_per_ns")

    gate = multi.get("slope_gate_pass")
    if gate is None:
        print("WARNING: slope_gate_pass missing/null — defaulting to slowest-rate (convention)",
              file=sys.stderr)
        gate = True

    if gate is False:
        fallback = plan.get("decided_params", {}).get("tg_slope_gate_fallback",
                                                      "highest_rate")
        if fallback not in ("highest_rate", "slowest_rate"):
            print(f"WARNING: unknown tg_slope_gate_fallback {fallback!r} — "
                  "using highest_rate", file=sys.stderr)
            fallback = "highest_rate"
        rate = rates[0] if fallback == "slowest_rate" else rates[-1]
    else:
        rate = rates[0]   # gate passed: slowest rate (DSC convention)
    raw_dir = os.path.dirname(os.path.abspath(args.multirate))
    tg_path = os.path.join(raw_dir, f"tg_r{_fmt_rate(rate)}", "tg_summary.json")

    print(f"TG_PATH={tg_path}")
    print(f"SLOPE_GATE={'true' if gate else 'false'}")


if __name__ == "__main__":
    main()
