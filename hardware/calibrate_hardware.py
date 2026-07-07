#!/usr/bin/env python3
"""
calibrate_hardware.py — one-command hardware calibration for PolyJarvis.

Host-matches the per-FF engine defaults in guides/polymer_rules.json:hardware_policy to
the box this clone runs on. The engine crossover is hardware-dependent (KOKKOS wins for
PPPM but loses on small UA cells on this GPU; another GPU/core-count can flip it), so a
fresh clone inherits numbers that are directional until re-measured here.

Two modes:
  --revalidate (DEFAULT) — confirm the SHIPPED by_forcefield default per FF on this host:
      run the exact engine/mpi/gpu the policy already ships (no engine re-search), gate it
      with a run-0 parity vs CPU (bench_accuracy_diff.py), and record host-matched ns/day.
      Uses the in-repo hardware/CALIB_* cells when --cell is omitted. This is the fresh-clone
      path: cheap, and it only confirms/measures — it does not re-decide engines.
  --full — fresh engine×config sweep per FF (the old matrix). Authoritative; needs explicit
      --cell/--ff pairs and ideally a drained box.

POLITE BY DEFAULT (shared boxes): only uses GPUs that are idle AND free of any compute
process from any user; caps MPI ranks against MEASURED system load while leaving >=25% of
cores free; runs everything `nice`d and sequentially; and SKIPS work that would contend.
A partial/contended/parity-failing/kokkos-fell-back run records evidence but leaves
`values_are_benchmarked=false`. Re-run on an idle box for the authoritative flip.

Usage:
  hardware/calibrate_hardware.py [--dry-run]           # revalidate shipped defaults, in-repo cells
  hardware/calibrate_hardware.py --full \\
      --cell /path/PCFF/cell.data --ff pcff \\
      --cell /path/UA/cell.data   --ff trappe          # fresh engine sweep
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
SCRIPTS = REPO / "scripts"
RULES = REPO / "guides" / "polymer_rules.json"
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SCRIPTS))         # hw_common lives with the runtime scripts
import benchmark_hardware as bh          # reuse politeness probes + detection + matrix
import hw_common                         # live_host() for the host fingerprint

HEADROOM_FRAC = 0.25                     # leave >=25% of physical cores for other users

# Shipped per-FF calibration cells (canonical names, committed in-repo) so a bare
# `/calibrate-hardware` needs no --cell args on a fresh clone. Missing entries are
# skipped with a warning (e.g. a cell still pending an EMC build).
CALIB_CELLS = {
    "pcff":   HERE / "CALIB_PCFF"   / "emc_build.data",
    "opls":   HERE / "CALIB_OPLS"   / "emc_build.data",
    "trappe": HERE / "CALIB_TRAPPE" / "emc_build.data",
    "gaff":   HERE / "CALIB_GAFF"   / "emc_build.data",
}
PPPM_FOR = {"pcff": True, "opls": True, "gaff": True, "trappe": False}  # UA has no kspace

LMP        = os.environ.get("LAMBDA_LAMMPS", bh.LMP_DEFAULT)
LMP_KOKKOS = os.environ.get("LAMBDA_LAMMPS_KOKKOS", bh.LMP_KOKKOS_DEFAULT)
CALIB_TMP  = Path("/tmp/polyjarvis/calib")
REVALIDATE_TIMEOUT_S = 1800             # generous per-run cap (timed run + two run-0 evals)


# --------------------------------------------------------------------------
# Host + politeness
# --------------------------------------------------------------------------
def detect_host() -> dict:
    # Single fingerprint definition (GPU count+model + a DIRECT core probe) shared with
    # hw_common.host_matches, so what we write here is exactly what the nudge compares against.
    return hw_common.live_host()


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
    cmd = ["nice", "-n", "19", sys.executable, str(HERE / "benchmark_hardware.py"),
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


def _carry_provenance(prior_probe: dict, probe: dict) -> None:
    """Carry hand-authored provenance sub-blocks (e.g. kokkos_offload_study) across a fresh
    directional_probe rebuild. Those record cross-host engine rationale that isn't re-derived
    by a throughput sweep, so wiping them on every calibration would lose real history."""
    for key in ("kokkos_offload_study",):
        if key in prior_probe:
            probe[key] = prior_probe[key]


def ingest(host: dict, per_ff: dict, date: str, clean: bool) -> None:
    hp = json.loads(RULES.read_text())["hardware_policy"]
    hp["host"] = host
    prior_probe = hp.get("directional_probe", {})
    probe = {}                                    # rebuild fresh — drop any stale prior-box keys
    hp["directional_probe"] = probe
    _carry_provenance(prior_probe, probe)
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
# Revalidate mode — confirm the SHIPPED per-FF default on THIS host (default mode).
# Runs the exact engine/mpi/gpu the policy already ships (no engine re-search), gates it
# with a run-0 parity vs CPU, and records host-matched ns/day. Use --full for a fresh
# engine×config sweep on a drained box.
# --------------------------------------------------------------------------
def arm_for(engine: str, fam: str) -> str:
    """Map a shipped engine choice to the benchmark_hardware execution arm that renders it.
    kokkos -> A3 (full-offload); gpu+trappe -> A1 (neigh on GPU, matching script_generator's
    use_trappe gating); gpu+PPPM or cpu -> A0 (neigh on CPU; cpu runs gpu=0 so arm flags are
    unused)."""
    if engine == "kokkos":
        return "A3"
    if engine == "gpu" and fam == "trappe":
        return "A1"
    return "A0"


def _run_once(cell: str, fam: str, arm_key: str, mpi: int, gpu_ids: list[int],
              steps: int, work: Path, tag: str):
    """One LAMMPS run via benchmark_hardware's deck-gen + runner. Returns (parsed, log_path)."""
    pppm = PPPM_FOR[fam]
    timestep = 2.0 if fam == "trappe" else 1.0
    master = work / f"{tag}_deck.in"
    params = bh.detect_params_file(cell)
    bh.make_input_generate(cell, fam, pppm, steps, timestep, params, master)
    arm = bh.ARMS[arm_key]
    lmp = LMP_KOKKOS if arm["engine"] == "kokkos" else LMP
    cfg = {"name": tag, "mpi": mpi, "gpu": len(gpu_ids)}
    r = bh.run_config(cfg, master, lmp, work, gpu_ids, REVALIDATE_TIMEOUT_S, arm)
    return r, work / tag / "bench.log"


def run_parity(cpu_log: Path, eng_log: Path, work: Path) -> dict:
    """Gate the shipped engine against the CPU reference on the SAME run-0 microstate via
    bench_accuracy_diff.py (PotEng/TotEng/E_bond… tolerances). tail-frac=1.0 because a run-0
    log has a single thermo row. Returns {verdict, cols}."""
    if not (cpu_log.exists() and eng_log.exists()):
        return {"verdict": "ERROR", "reason": "missing parity log(s)"}
    out = work / "parity.json"
    subprocess.run([sys.executable, str(HERE / "bench_accuracy_diff.py"),
                    "--baseline", f"CPU={cpu_log}", "--variant", f"ENGINE={eng_log}",
                    "--tail-frac", "1.0", "--out", str(out)],
                   check=False, capture_output=True, text=True)
    if not out.exists():
        return {"verdict": "ERROR", "reason": "diff produced no output"}
    v = (json.loads(out.read_text()).get("variants") or [{}])[0]
    return {"verdict": v.get("verdict", "ERROR"), "cols": v.get("cols", {})}


def revalidate_ff(fam: str, cell: str, default: dict, st: dict, steps: int,
                  dry: bool, kokkos_ok: bool) -> dict:
    """Re-validate one FF's shipped default on this host: run it (timed) + run-0 parity vs CPU."""
    engine = default.get("engine", "gpu")
    mpi = int(default.get("mpi", 1) or 1)
    gpu_per_run = 0 if engine == "cpu" else int(default.get("gpu_per_run", 1) or 1)
    notes: list[str] = []
    fell_back = False
    if engine == "kokkos" and not kokkos_ok:
        # No KOKKOS binary on this box — validate the DOCUMENTED fallback instead (engine=gpu,
        # mpi=4) and flag it: the shipped kokkos default is NOT proven here.
        engine, mpi, gpu_per_run, fell_back = "gpu", 4, 1, True
        notes.append("KOKKOS binary absent — validated documented fallback engine=gpu mpi=4 "
                     "instead; build LAMBDA_LAMMPS_KOKKOS to unlock the kokkos default.")
    arm = arm_for(engine, fam)
    need_gpu = gpu_per_run

    # politeness gate (same discipline as the full sweep)
    if need_gpu and len(st["free_gpus"]) < need_gpu:
        return {"ff": fam, "status": "skipped", "engine": engine,
                "reason": f"needs {need_gpu} idle GPU(s), free={st['free_gpus']}", "notes": notes}
    if mpi > st["mpi_cap"]:
        return {"ff": fam, "status": "skipped", "engine": engine,
                "reason": f"mpi {mpi} > polite cap {st['mpi_cap']} "
                          f"(busy~{st['busy_cores']}, headroom {st['headroom']})", "notes": notes}
    gpu_ids = st["free_gpus"][:need_gpu]
    config_name = (f"gpu{need_gpu}_mpi{mpi}" if need_gpu else f"cpu_mpi{mpi}")

    if dry:
        return {"ff": fam, "status": "planned", "engine": engine, "arm": arm, "mpi": mpi,
                "gpu_per_run": need_gpu, "gpu_ids": gpu_ids, "config_name": config_name,
                "cell": cell, "fell_back": fell_back, "notes": notes}

    work = CALIB_TMP / fam
    work.mkdir(parents=True, exist_ok=True)
    # 1) timed shipped config -> host-matched ns/day
    timed, _ = _run_once(cell, fam, arm, mpi, gpu_ids, steps, work, "timed")
    # 2) run-0 parity: shipped engine vs CPU, mpi=1 both, identical microstate
    _, eng_log = _run_once(cell, fam, arm, 1, gpu_ids, 0, work, "p0_engine")
    _, cpu_log = _run_once(cell, fam, "A0", 1, [], 0, work, "p0_cpu")
    parity = run_parity(cpu_log, eng_log, work)

    return {"ff": fam, "status": timed.get("status", "failed"), "engine": engine, "arm": arm,
            "mpi": mpi, "gpu_per_run": need_gpu, "config_name": config_name, "cell": cell,
            "ns_per_day": timed.get("ns_per_day"), "atoms": timed.get("atoms"),
            "parity": parity, "fell_back": fell_back, "notes": notes,
            "sections_pct": timed.get("sections_pct", {})}


def ingest_revalidate(host: dict, records: list[dict], st: dict, date: str) -> bool:
    """Write the revalidation evidence into hardware_policy. Flips values_are_benchmarked=true
    only on a clean host-matched pass: every targeted FF ran, every parity PASSed, no kokkos
    fallback, and the CPU was uncontended. Engine CHOICES are unchanged (revalidate confirms,
    it does not re-decide). Returns the clean flag."""
    hp = json.loads(RULES.read_text())["hardware_policy"]
    hp["host"] = host
    prior_probe = hp.get("directional_probe", {})
    probe: dict = {}
    hp["directional_probe"] = probe
    _carry_provenance(prior_probe, probe)
    probe["measured_on"] = (f"{host['gpus']}x {host['gpu_model']} / "
                            f"{host['phys_cores']} phys cores (calibrate_hardware.py --revalidate)")
    probe["date"] = date
    probe["mode"] = ("revalidate — ran the shipped by_forcefield default per FF (no engine "
                     "re-search) + run-0 parity vs CPU; records host-matched ns/day. Use "
                     "--full for a fresh engine×config sweep on a drained box.")
    cells = probe.setdefault("cells", {})
    cells_atoms = probe.setdefault("cells_atoms", {})
    rec_by_ff = probe.setdefault("recommended_by_ff", {})

    ran = [r for r in records if r.get("status") == "ok"]
    skipped = [r for r in records if r.get("status") not in ("ok", "planned")]
    any_fallback = any(r.get("fell_back") for r in records)
    all_pass = bool(ran) and all((r.get("parity") or {}).get("verdict") == "PASS" for r in ran)

    for r in ran:
        fam = r["ff"]
        cells[fam] = r.get("cell")
        if r.get("atoms"):
            cells_atoms[fam] = r["atoms"]
        probe[f"{fam}_ns_per_day"] = {r["config_name"]: r["ns_per_day"]}
        rec_by_ff[fam] = {"name": r["config_name"], "mpi": r["mpi"], "gpu": r["gpu_per_run"],
                          "ns_per_day": r["ns_per_day"], "cell_atoms": r.get("atoms"),
                          "engine": r["engine"],
                          "parity": (r.get("parity") or {}).get("verdict"),
                          "fell_back": r.get("fell_back", False)}

    clean = (bool(ran) and not skipped and all_pass and not any_fallback
             and st["busy_cores"] <= st["headroom"])
    if clean:
        hp["values_are_benchmarked"] = True
        probe["calibration_note"] = ("clean host-matched revalidation — every shipped default ran "
                                     "and passed run-0 parity on this box; values_are_benchmarked=true.")
    else:
        hp["values_are_benchmarked"] = False
        why = []
        if skipped:
            why.append(f"skipped {[r['ff'] for r in skipped]} (box contended)")
        if not all_pass:
            why.append("a parity check did not PASS")
        if any_fallback:
            why.append("a KOKKOS default fell back (binary absent) — build it and re-run")
        if st["busy_cores"] > st["headroom"]:
            why.append(f"CPU contended (busy~{st['busy_cores']} > headroom {st['headroom']})")
        probe["calibration_note"] = ("partial revalidation — evidence recorded, "
                                     "values_are_benchmarked left false: " + "; ".join(why))
    splice_hardware_policy(hp)
    return clean


def run_revalidate(args, host: dict) -> int:
    try:
        os.nice(19)                       # be polite even on direct (non-subprocess) runs
    except OSError:
        pass
    st = polite_state(host["phys_cores"], args.allow_busy)
    hp = json.loads(RULES.read_text())["hardware_policy"]
    by_ff = hp.get("by_forcefield", {})

    # cell set: explicit --cell/--ff pairs, else the in-repo manifest (existing cells only)
    if args.cell:
        pairs = list(zip(args.ff, args.cell))
    else:
        pairs = [(fam, str(p)) for fam, p in CALIB_CELLS.items() if Path(p).exists()]
        missing = [fam for fam, p in CALIB_CELLS.items() if not Path(p).exists()]
        if missing:
            print(f"   note: no in-repo cell yet for {missing} — skipping "
                  f"(build + commit hardware/CALIB_<FAM>/emc_build.data to include)")

    kokkos_ok = bh.kokkos_binary_ok(LMP_KOKKOS)
    print("== PolyJarvis hardware revalidation (shipped per-FF defaults) ==")
    print(f"   host: {host['gpus']}x {host['gpu_model']}, {host['phys_cores']} phys cores")
    print(f"   polite state: free_gpus={st['free_gpus']} busy_cores~{st['busy_cores']} "
          f"headroom={st['headroom']} mpi_cap={st['mpi_cap']}"
          + ("  (--allow-busy: gating OFF)" if args.allow_busy else ""))
    print(f"   kokkos binary: {'OK ' + LMP_KOKKOS if kokkos_ok else 'ABSENT (kokkos FFs fall back to gpu/mpi4)'}")
    if not pairs:
        print("ERROR: no calibration cells available (none in-repo, none passed via --cell)",
              file=sys.stderr)
        return 1

    records = []
    for fam, cell in pairs:
        default = by_ff.get(fam, {})
        r = revalidate_ff(fam, cell, default, st, args.steps, args.dry_run, kokkos_ok)
        records.append(r)
        if args.dry_run:
            if r["status"] == "planned":
                print(f"   PLAN {fam:<7} engine={r['engine']} arm={r['arm']} "
                      f"{r['config_name']} gpu_ids={r['gpu_ids']}"
                      + ("  [kokkos fallback]" if r["fell_back"] else ""))
            else:
                print(f"   SKIP {fam:<7} — {r.get('reason')}")
            for n in r.get("notes", []):
                print(f"        {n}")
            continue
        if r["status"] == "ok":
            print(f"   {fam:<7} {r['config_name']:<11} {r['ns_per_day']:>8.2f} ns/day  "
                  f"parity={r['parity']['verdict']}"
                  + ("  [kokkos fallback]" if r["fell_back"] else ""))
        else:
            print(f"   {fam:<7} {r['status']}: {r.get('reason','')}")
        for n in r.get("notes", []):
            print(f"        {n}")

    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0

    clean = ingest_revalidate(host, records, st, args.date)
    print(f"\n== wrote hardware_policy → {RULES} ==")
    print(f"   values_are_benchmarked = {clean}"
          f"  ({'clean host-matched sweep' if clean else 'partial — evidence only'})")
    return 0


# --------------------------------------------------------------------------
# Full sweep — fresh engine×config search per FF (drained-box authoritative mode, --full)
# --------------------------------------------------------------------------
def run_full(args, host: dict) -> int:
    st = polite_state(host["phys_cores"], args.allow_busy)
    runnable, skipped = plan_configs(host["phys_cores"], st, args.allow_busy)
    only_names = [c["name"] for c in runnable]

    print("== PolyJarvis hardware calibration (full sweep) ==")
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

    per_ff: dict = {}
    for cell, ff in zip(args.cell, args.ff):
        d = benchmark_cell(cell, ff, PPPM_FOR[ff], args.steps, st,
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


# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cell", action="append", default=[],
                    help="path to a built .data cell (repeatable, paired with --ff). "
                         "Omit in --revalidate mode to use the in-repo hardware/CALIB_* cells.")
    ap.add_argument("--ff", action="append", default=[],
                    choices=["pcff", "opls", "trappe", "gaff"],
                    help="force-field family for the matching --cell (repeatable)")
    ap.add_argument("--pppm", action="append", default=None,
                    help="(unused placeholder; pppm is inferred from --ff)")
    ap.add_argument("--full", action="store_true",
                    help="fresh engine×config sweep per FF (drained-box authoritative mode). "
                         "Default is --revalidate: confirm the shipped per-FF defaults on this host.")
    ap.add_argument("--steps", type=int, default=4000, help="MD steps per timed config")
    ap.add_argument("--date", default=datetime.date.today().isoformat(),
                    help="measurement date stamp (default: today)")
    ap.add_argument("--allow-busy", action="store_true",
                    help="DEDICATED/DRAINED BOX ONLY: disable politeness gating")
    ap.add_argument("--dry-run", action="store_true",
                    help="show the planned polite work; write nothing")
    args = ap.parse_args()

    if len(args.cell) != len(args.ff):
        print("ERROR: each --cell needs a matching --ff (same order/count)", file=sys.stderr)
        return 2
    if args.full and not args.cell:
        print("ERROR: --full needs explicit --cell/--ff pairs (the full sweep is not "
              "auto-celled). Use the default --revalidate for the in-repo cells.", file=sys.stderr)
        return 2

    host = detect_host()
    return run_full(args, host) if args.full else run_revalidate(args, host)


if __name__ == "__main__":
    raise SystemExit(main())
