#!/usr/bin/env python3
"""Real failure injection: perturb a built cell so a chosen Finding code actually fires.

This is the benchmark's core. Each injector is a surgical edit to a real EMC cell plus the
`Finding.code` that edit is claimed to produce, and `verify()` proves the claim by running
the SAME validation call run_campaign.py makes before equilibration:

    inspect_data_file(data_file, lj_cutoff, target_density_gcm3, nchain, params_file)
      -> validation.errors
         SIZE_*  -> StageHalt -> SIZE_MIN_IMAGE_VIOLATION -> finite_size_rebuild  (cap 2)
         other   -> halted     -> BUILD_CELL_INVALID       -> agent_only, escalates

Two properties make this a benchmark rather than a mock:

  * The clean cell is checked too, and must produce NO error. An injector that "fires" on a
    cell that was already failing measures nothing. `params_file` is what makes that control
    meaningful -- without it every EMC cell reports five spurious "'Pair Coeffs' section
    missing" errors, because the coefficients live in the .params, not the .data.
  * The code is not asserted from a string table; it is derived from the real error list by
    the same SIZE_/other split run_campaign.py:512-534 performs.

Injection is at the cell, so a trial costs SECONDS and no MD. That is deliberate: the point
is to exercise the remedy ladder's routing and caps, and the ladder cannot tell a cell that
was corrupted from one that was built badly.

    python3 benchmarks/recovery_r2/injectors.py --verify   # prove every injector fires
    python3 benchmarks/recovery_r2/injectors.py --list
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine"))

#: run_campaign.py's own defaults at the validation call site.
DEFAULT_CUTOFF = 12.0
DEFAULT_TARGET_DENSITY = 1.2
DEFAULT_NCHAIN = 10


def _atoms_start(lines: list[str]) -> int:
    """Index of the first atom row. 'Atoms' header, then a blank line."""
    for n, line in enumerate(lines):
        if line.strip().split("#")[0].strip() == "Atoms":
            return n + 2
    raise ValueError("no Atoms section")


# ---------------------------------------------------------------- injectors

def inject_net_charge(text: str, delta: float = 0.9) -> str:
    """Perturb one atom's partial charge. The cell stops being charge-neutral, which PPPM
    requires -- the real-world shape of a RESP/charge-assignment failure."""
    lines = text.split("\n")
    i = _atoms_start(lines)
    parts = lines[i].split()
    parts[3] = f"{float(parts[3]) + delta:.4f}"
    lines[i] = " ".join(parts)
    return "\n".join(lines)


def inject_truncate_atoms(text: str, rows: int = 3) -> str:
    """Drop atom rows while the header count stays put -- round-1's F6 shape. Bonds, angles
    and dihedrals still reference the removed ids."""
    lines = text.split("\n")
    i = _atoms_start(lines)
    del lines[i:i + rows]
    return "\n".join(lines)


def inject_collapse_box(text: str) -> str:
    """Zero one box dimension: the signature of a truncated or half-written data file."""
    lines = text.split("\n")
    for n, line in enumerate(lines):
        if "xlo xhi" in line:
            lines[n] = "0.0 0.0 xlo xhi"
            break
    else:
        raise ValueError("no xlo xhi line")
    return "\n".join(lines)


@dataclass(frozen=True)
class Injector:
    id: str
    target_code: str
    fn: Callable[..., str] | None      #: None = the perturbation is a knob, not a file edit
    knobs: dict
    what: str
    round1: str = ""

    def apply(self, text: str) -> str:
        return self.fn(text) if self.fn else text


INJECTORS = [
    Injector("net_charge", "BUILD_CELL_INVALID", inject_net_charge, {},
             "Add +0.9 e to one atom's partial charge; the cell is no longer charge-neutral.",
             round1="(new -- no round-1 equivalent)"),
    Injector("truncate_atoms", "BUILD_CELL_INVALID", inject_truncate_atoms, {},
             "Delete 3 atom rows, leaving the header over-counting and the topology "
             "referencing ids that no longer exist.",
             round1="F6 (data-file corruption)"),
    Injector("collapse_box", "BUILD_CELL_INVALID", inject_collapse_box, {},
             "Zero the x box dimension -- a truncated data file."),
    Injector("undersized_cell", "SIZE_MIN_IMAGE_VIOLATION", None,
             {"lj_cutoff": 40.0},
             "Leave the cell intact and demand a cutoff the box cannot honour, so the "
             "compressed cell would self-image. Routes to finite_size_rebuild, the one "
             "automatic remedy whose success shows up as a different cell."),
]


# ---------------------------------------------------------------- the production check

def classify(data_path: Path, params_path: Path, *, lj_cutoff=DEFAULT_CUTOFF,
             nchain=DEFAULT_NCHAIN, target_density=DEFAULT_TARGET_DENSITY) -> tuple[str | None, list[str]]:
    """Run run_campaign's own validation call and apply its own SIZE_/other routing.

    Returns (Finding.code or None, errors). Imported lazily: the LAMMPS engine module is
    heavy and logs on import, and --list should not pay for it.
    """
    import server as lammps  # noqa: PLC0415
    info = lammps.inspect_data_file(
        data_file=str(data_path), lj_cutoff=lj_cutoff,
        target_density_gcm3=target_density, nchain=nchain,
        params_file=str(params_path) if params_path else "")
    errors = list((info.get("validation") or {}).get("errors") or [])
    size = [e for e in errors if e.startswith("SIZE_")]
    other = [e for e in errors if not e.startswith("SIZE_")]
    # run_campaign.py:512-534 -- SIZE_ is raised FIRST so it reaches finite_size_rebuild
    # rather than being folded into a generic invalid-cell escalation.
    if size:
        return "SIZE_MIN_IMAGE_VIOLATION", errors
    if other:
        return "BUILD_CELL_INVALID", errors
    return None, errors


def verify(cell_data: Path, cell_params: Path) -> dict:
    """Prove each injector produces its target code, and that the clean cell produces none."""
    text = cell_data.read_text()
    clean_code, clean_errors = classify(cell_data, cell_params)
    results = {"cell": str(cell_data),
               "control": {"code": clean_code, "errors": clean_errors,
                           "ok": clean_code is None}}
    rows, failures = [], []
    if clean_code is not None:
        failures.append(f"CONTROL: clean cell already fails with {clean_code} -- every "
                        f"injection below would be measuring that, not itself")
    tmp = Path(tempfile.mkdtemp(prefix="inject_"))
    for inj in INJECTORS:
        path = tmp / f"{inj.id}.data"
        path.write_text(inj.apply(text))
        code, errors = classify(path, cell_params, **inj.knobs)
        ok = code == inj.target_code
        rows.append({"id": inj.id, "target_code": inj.target_code, "got": code,
                     "fired": ok, "knobs": inj.knobs,
                     "evidence": (errors[0][:140] if errors else None)})
        if not ok:
            failures.append(f"{inj.id}: expected {inj.target_code}, got {code}")
    results["injectors"] = rows
    results["failures"] = failures
    return results


def find_cell() -> tuple[Path, Path] | tuple[None, None]:
    """Any completed build's cell. Read-only -- injection always works on a copy."""
    for state in sorted((REPO_ROOT / "data").glob("*/workflow_state.json")):
        for data in sorted(state.parent.glob("attempts/build/*/work/cell/*.data")):
            params = next(iter(data.parent.glob("*.params")), None)
            if params:
                return data, params
    return None, None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--cell", help="path to a .data file; default: any completed build")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.list or not args.verify:
        print(f"{len(INJECTORS)} injectors\n")
        for i in INJECTORS:
            print(f"  {i.id:16s} -> {i.target_code:26s} {i.what}")
            if i.round1:
                print(f"  {'':16s}    round 1: {i.round1}")
        return 0

    if args.cell:
        data = Path(args.cell)
        params = next(iter(data.parent.glob("*.params")), None)
    else:
        data, params = find_cell()
    if not data:
        print("no completed build with a cell + params found under data/")
        return 1

    result = verify(data, params)
    if args.json:
        print(json.dumps(result, indent=2))
        return 1 if result["failures"] else 0
    print(f"cell:    {data}")
    ctrl = result["control"]
    print(f"control: {'PASS -- clean cell produces no error' if ctrl['ok'] else 'FAIL -- ' + str(ctrl['errors'])[:200]}\n")
    for row in result["injectors"]:
        print(f"  {'FIRED' if row['fired'] else 'MISS ':5s} {row['id']:16s} -> {row['got']}")
        if row["evidence"]:
            print(f"        {row['evidence']}")
    print(f"\n{'PASS' if not result['failures'] else 'FAIL'}: "
          f"{sum(r['fired'] for r in result['injectors'])}/{len(result['injectors'])} injectors fire their target code")
    for f in result["failures"]:
        print(f"  {f}")
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
