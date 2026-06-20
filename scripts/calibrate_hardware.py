#!/usr/bin/env python3
"""
calibrate_hardware.py — one-command hardware calibration for PolyJarvis.

Closes the loop that benchmark_hardware.py leaves open. It runs the throughput
matrix on one or more representative cells, then writes the measured optimum back
into guides/polymer_rules.json:hardware_policy — the `host` block, the
`directional_probe` evidence, `values_are_benchmarked`, and (only on a clean,
uncontended sweep) the per-FF defaults that gen_prompt.py:resolve_hardware() consumes.

POLITE BY DEFAULT (shared boxes): only benchmarks GPUs that are idle AND free of any
compute process from any user; caps MPI ranks against MEASURED system load while
leaving >=25% of cores free; runs everything `nice`d and strictly sequentially; and
SKIPS configs that would contend. Because a contended sweep can mislead (e.g. UA looks
GPU-favoured only because the CPU is saturated), a partial/contended sweep records the
evidence but does NOT overwrite the consumed `by_forcefield` defaults and leaves
`values_are_benchmarked=false`. Re-run on a drained box (or with --allow-busy on a
dedicated box) for the authoritative update.

Usage:
  scripts/calibrate_hardware.py \
      --cell /path/PCFF/cell.data --ff pcff --pppm \
      --cell /path/UA/cell.data   --ff trappe \
      [--dry-run] [--steps 4000] [--date YYYY-MM-DD] [--allow-busy]
"""
from __future__ import annotations

import argparse
import datetime
import json
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
RULES = REPO / "guides" / "polymer_rules.json"
sys.path.insert(0, str(SCRIPTS))
import benchmark_hardware as bh          # reuse politeness probes + detection + matrix

HEADROOM_FRAC = 0.25                     # leave >=25% of physical cores for other users


# --------------------------------------------------------------------------
# Host + politeness
# --------------------------------------------------------------------------
def detect_host() -> dict:
    phys = bh.detect_phys_cores()
    n_gpu = len(bh.gpu_status())
    model = "unknown"
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=15).stdout
        names = [l.strip() for l in out.strip().splitlines() if l.strip()]
        if names:
            model = names[0]
    except Exception:
        pass
    return {"gpus": n_gpu, "gpu_model": model, "phys_cores": phys}


def polite_state(phys: int, allow_busy: bool) -> dict:
    """Snapshot of what we may use right now without contending."""
    free = bh.idle_gpu_ids()
    busy = 0 if allow_busy else bh.busy_cores(phys)
    headroom = 0 if allow_busy else max(1, round(HEADROOM_FRAC * phys))
    cap = phys if allow_busy else max(1, phys - busy - headroom)
    return {"free_gpus": free, "busy_cores": busy, "headroom": headroom, "mpi_cap": cap}


def plan_configs(phys: int, st: dict, allow_busy: bool):
    """Split the scaled matrix into (runnable, skipped[(name,reason)]) for current load."""
    runnable, skipped = [], []
    for c in bh._build_configs(phys):
        if not allow_busy and c["mpi"] > st["mpi_cap"]:
            skipped.append((c["name"],
                            f"mpi {c['mpi']} > polite cap {st['mpi_cap']} "
                            f"(busy~{st['busy_cores']}, headroom {st['headroom']})"))
        elif c["gpu"] > 0 and len(st["free_gpus"]) < c["gpu"]:
            skipped.append((c["name"], f"needs {c['gpu']} idle/free GPU(s), free={st['free_gpus']}"))
        else:
            runnable.append(c)
    return runnable, skipped


# --------------------------------------------------------------------------
# Benchmark one cell (delegates to benchmark_hardware.py, nice'd + polite)
# --------------------------------------------------------------------------
def benchmark_cell(cell: str, ff: str, pppm: bool, steps: int, st: dict,
                   only_names: list[str], dry: bool, allow_busy: bool) -> dict | None:
    label = f"calib_{ff}_{Path(cell).parent.name}"
    out_json = Path("/tmp/polyjarvis/bench") / label / "benchmark.json"
    cmd = ["nice", "-n", "19", sys.executable, str(SCRIPTS / "benchmark_hardware.py"),
           "--data", cell, "--ff", ff, "--label", label,
           "--steps", str(steps), "--out", str(out_json),
           "--pppm" if pppm else "--no-pppm"]
    if only_names:
        cmd += ["--only", ",".join(only_names)]
    for gid in st["free_gpus"]:                 # let GPU configs pin to the free GPUs
        cmd += ["--gpu-id", str(gid)]
    if allow_busy:
        cmd += ["--allow-busy"]
    if dry:
        cmd += ["--dry-run"]
    print(f"\n>> {ff} cell: {cell}")
    print("   $ " + " ".join(shlex.quote(x) for x in cmd))
    subprocess.run(cmd, check=False)
    if dry or not out_json.exists():
        return None
    return json.loads(out_json.read_text())


# --------------------------------------------------------------------------
# Ingest results into polymer_rules.json:hardware_policy (splice — preserve rest)
# --------------------------------------------------------------------------
def _hp_span(text: str) -> tuple[int, int]:
    """Byte span [start,end) of the hardware_policy *value object* {...}."""
    i = text.index('"hardware_policy"')
    brace = text.index("{", i)
    depth, j, in_str, esc = 0, brace, False, False
    while j < len(text):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return brace, j + 1
        j += 1
    raise ValueError("could not find end of hardware_policy object")


def splice_hardware_policy(new_hp: dict) -> None:
    text = RULES.read_text()
    start, end = _hp_span(text)
    body = json.dumps(new_hp, indent=2).replace("\n", "\n  ")   # nest under the 2-space key
    RULES.write_text(text[:start] + body + text[end:])


def ingest(host: dict, per_ff: dict, date: str, clean: bool) -> None:
    hp = json.loads(RULES.read_text())["hardware_policy"]
    hp["host"] = host
    probe = {}                                    # rebuild fresh — drop any stale prior-box keys
    hp["directional_probe"] = probe
    probe["measured_on"] = (f"{host['gpus']}x {host['gpu_model']} / "
                            f"{host['phys_cores']} phys cores (calibrate_hardware.py)")
    probe["date"] = date
    probe["cells"] = {ff: d["data_file"] for ff, d in per_ff.items()}
    probe["ff_coverage_note"] = (
        "Benchmarked per FORCE-FIELD FAMILY, not per polymer template: the mpi/gpu optimum is "
        "set by the interaction-style mix (pair + k-space), which the FF family fixes, while the "
        "template only changes atom identities and cell size. The matrix branches on one bit "
        "(PPPM on/off), so two regimes cover all four FFs: pcff/opls/gaff are all-atom + PPPM "
        "(measured via pcff, the heaviest of the three -> conservative proxy for opls/gaff); "
        "trappe is united-atom, no k-space. Add an explicit --cell ... --ff opls only if you need "
        "a directly-measured OPLS number rather than the pcff-bracketed default.")
    rec_by_ff = probe.setdefault("recommended_by_ff", {})
    cells_atoms = probe.setdefault("cells_atoms", {})
    for ff, d in per_ff.items():
        ok = [r for r in d["results"] if r.get("status") == "ok"]
        probe[f"{ff}_ns_per_day"] = {r["name"]: r["ns_per_day"] for r in ok}
        # atom count of the benchmark cell — the size reference the planner scales from
        # (engine/gpu crossover is size-dependent; see directional_probe.ff_coverage_note)
        atoms = next((r.get("atoms") for r in [d.get("recommended")] + ok
                      if r and r.get("atoms")), None)
        if atoms:
            cells_atoms[ff] = atoms
        rec = d.get("recommended")
        if rec:
            rec_by_ff[ff] = {"name": rec["name"], "mpi": rec["mpi"],
                             "gpu": rec["gpu"], "ns_per_day": rec["ns_per_day"],
                             "cell_atoms": rec.get("atoms")}

    if clean:
        for ff, d in per_ff.items():
            fam = ff                                         # ff IS the by_forcefield key
            rec = d.get("recommended")
            ent = hp.get("by_forcefield", {}).get(fam)
            if not rec or ent is None:
                continue
            ent["engine"] = "gpu" if rec["gpu"] > 0 else "cpu"
            ent["gpu_per_run"] = rec["gpu"] if rec["gpu"] > 0 else 0
            ent["mpi_single_run_hint"] = rec["mpi"]
        hp["values_are_benchmarked"] = True
        probe["calibration_note"] = "clean uncontended sweep — by_forcefield updated"
    else:
        hp["values_are_benchmarked"] = False
        probe["calibration_note"] = ("partial/contended sweep on a shared box — evidence "
                                     "recorded but by_forcefield left unchanged; re-run on a "
                                     "drained box (or --allow-busy on a dedicated box) to "
                                     "authoritatively update the consumed defaults")
    splice_hardware_policy(hp)


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cell", action="append", default=[], required=True,
                    help="path to a built .data cell (repeatable, paired with --ff)")
    ap.add_argument("--ff", action="append", default=[],
                    choices=["pcff", "opls", "trappe", "gaff"],
                    help="force-field family for the matching --cell (repeatable)")
    ap.add_argument("--pppm", action="append", default=None,
                    help="(unused placeholder; pppm is inferred from --ff)")
    ap.add_argument("--steps", type=int, default=4000, help="MD steps per config")
    ap.add_argument("--date", default=datetime.date.today().isoformat(),
                    help="measurement date stamp (default: today)")
    ap.add_argument("--allow-busy", action="store_true",
                    help="DEDICATED/DRAINED BOX ONLY: disable politeness gating")
    ap.add_argument("--dry-run", action="store_true",
                    help="show the planned polite matrix per cell; write nothing")
    args = ap.parse_args()

    if len(args.cell) != len(args.ff):
        print("ERROR: each --cell needs a matching --ff (same order/count)", file=sys.stderr)
        return 2

    host = detect_host()
    st = polite_state(host["phys_cores"], args.allow_busy)
    runnable, skipped = plan_configs(host["phys_cores"], st, args.allow_busy)
    only_names = [c["name"] for c in runnable]

    print("== PolyJarvis hardware calibration ==")
    print(f"   host: {host['gpus']}x {host['gpu_model']}, {host['phys_cores']} phys cores")
    print(f"   polite state: free_gpus={st['free_gpus']} busy_cores~{st['busy_cores']} "
          f"headroom={st['headroom']} mpi_cap={st['mpi_cap']}"
          + ("  (--allow-busy: gating OFF)" if args.allow_busy else ""))
    print(f"   will run: {only_names or '(none — box too busy right now)'}")
    for name, why in skipped:
        print(f"   skip {name:<11} — {why}")
    if not runnable:
        print("\nNo configs can run politely right now. Try again when the box is idle, "
              "or pass --allow-busy on a dedicated box.", file=sys.stderr)
        return 1

    pppm_for = {"pcff": True, "opls": True, "gaff": True, "trappe": False}
    per_ff: dict = {}
    for cell, ff in zip(args.cell, args.ff):
        d = benchmark_cell(cell, ff, pppm_for[ff], args.steps, st,
                           only_names, args.dry_run, args.allow_busy)
        if d is not None:
            per_ff[ff] = d

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0
    if not per_ff:
        print("ERROR: no benchmark results produced", file=sys.stderr)
        return 1

    # "clean" = full scaled matrix ran with no resource skips and uncontended CPU
    clean = (not skipped) and st["busy_cores"] <= st["headroom"]
    ingest(host, per_ff, args.date, clean)
    print(f"\n== wrote hardware_policy → {RULES} ==")
    print(f"   values_are_benchmarked = {clean}  ({'clean sweep' if clean else 'partial/contended — evidence only'})")
    for ff, d in per_ff.items():
        rec = d.get("recommended")
        if rec:
            print(f"   {ff}: best {rec['name']} = {rec['ns_per_day']:.2f} ns/day")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
