#!/usr/bin/env python3
"""
validate_result.py — Validate a worker RESULT block before inter-stage handoff.

Usage:
  python3 scripts/validate_result.py --stage <STAGE> --result '<YAML block>'

Stages: build | equil | tg | tg-analysis | deform | property-analysis

Exit 0 if valid, exit 1 with error messages if any required field is missing or null.

Can also be used as a library:
  from scripts.validate_result import validate_result
  errors = validate_result("build", result_dict)  # returns list of error strings
"""

import argparse
import re
import sys
from typing import Any

REQUIRED_FIELDS: dict[str, list[str]] = {
    "build": ["data_path", "lammps_flags", "polymer_class", "ff"],
    "equil": ["chain_id", "expected_equil_data", "npt_prod_log_path", "monitor_command"],
    "tg": ["run_id", "tg_log_path", "monitor_command"],
    "tg-analysis": ["run_name", "Tg_K", "Tg_fit_quality", "Tg_r_squared", "overall_verdict", "output_dir"],
    "deform": ["run_id", "monitor_command", "deform_log_path", "is_glassy"],
    "property-analysis": [
        "run_name", "equilibrated", "density_gcm3", "bulk_modulus_GPa",
        "bulk_modulus_method", "equilibration_overall_pass", "overall_verdict",
        "run_summary_path", "output_dir", "graphs_dir",
    ],
}

NULL_VALUES = {"null", "none", "n/a", "<fill>", ""}


def parse_result_block(text: str) -> dict[str, Any]:
    """Parse a RESULT: YAML block from worker output into a flat dict."""
    result: dict[str, Any] = {}
    in_result = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "RESULT:":
            in_result = True
            continue
        if in_result:
            if stripped.startswith("- ") or not stripped:
                continue
            if ":" in stripped and not stripped.startswith("#"):
                key, _, val = stripped.partition(":")
                result[key.strip()] = val.strip()
    return result


def validate_result(stage: str, result: dict[str, Any]) -> list[str]:
    """Return a list of error strings. Empty list = valid."""
    required = REQUIRED_FIELDS.get(stage)
    if required is None:
        return [f"Unknown stage '{stage}'. Valid: {', '.join(REQUIRED_FIELDS)}"]
    errors = []
    for field in required:
        val = result.get(field)
        if val is None:
            errors.append(f"Missing required field: {field}")
        elif str(val).strip().lower() in NULL_VALUES:
            errors.append(f"Required field '{field}' is null/empty (got: {val!r})")
    return errors


def main() -> None:
    p = argparse.ArgumentParser(description="Validate a PolyJarvis worker RESULT block.")
    p.add_argument("--stage", required=True, choices=list(REQUIRED_FIELDS))
    p.add_argument("--result", required=True, help="Raw RESULT block text (YAML-ish)")
    args = p.parse_args()

    parsed = parse_result_block(args.result)
    if not parsed:
        # Try treating --result as already-parsed key: value lines
        for line in args.result.splitlines():
            if ":" in line:
                k, _, v = line.partition(":")
                parsed[k.strip()] = v.strip()

    errors = validate_result(args.stage, parsed)
    if errors:
        print(f"RESULT validation FAILED for stage '{args.stage}':")
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print(f"RESULT validation PASSED for stage '{args.stage}' ({len(parsed)} fields parsed).")
        sys.exit(0)


if __name__ == "__main__":
    main()
