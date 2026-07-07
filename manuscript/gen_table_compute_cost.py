#!/usr/bin/env python3
"""Computational-cost audit harvester.

Harvests wall-clock time from the retained LAMMPS logs and reports cost split by
force-field class (the two cost tiers of the compute-cost table). Each stage is
classified GPU vs CPU from acceleration-init lines in its log/stdout.

Harvest rule: sum `Loop time of T on P procs for M steps` (M>0) over all
`<RUN>/lammps/**/*.log`, excluding killed/partial/born/archive paths and the duplicate
`*_run.log` / `*_stdout.log` / `*wrapper*` copies. wall_h = sum(T)/3600;
core_h = sum(T*P)/3600.

Outputs:
  manuscript/csv/compute_cost.csv         (per-run: wall_h, core_h, sim_ns, cores, n_logs)
  manuscript/csv/compute_cost_class.csv   (per force-field-class aggregate)
and prints the two per-class summary rows.
"""
import csv
import glob
import os
import re

DATA = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "csv")
RUN_RE = re.compile(r"^(cis-PBD|PE|PEG|PLA|PMMA|PS|PSU|PVC|PEEK)\d+$")
FAM_RE = re.compile(r"\d+$")
LOOP = re.compile(
    r"Loop time of ([\d.]+) on (\d+) procs for (\d+) steps with (\d+) atoms")
BAD = ("_killed", "_gpu_partial", "archive", "contaminated", "_run.log",
       "_stdout.log", "wrapper", "born")     # "born" excludes the removed Born method

# Force-field class per family (UA = lj/cut TraPPE-UA; AA = PCFF lj/class2 + PPPM).
FF_CLASS = {
    "cis-PBD": "UA", "PE": "UA",
    "PLA": "AA", "PMMA": "AA", "PSU": "AA", "PVC": "AA", "PEEK": "AA",
    "PEG": "AA", "PS": "AA",
}
FF_LABEL = {"UA": "United-atom (TraPPE-UA, lj/cut)",
            "AA": "All-atom (PCFF, lj/class2 + PPPM)"}
UA = {"PE", "cis-PBD"}
GPUINIT = re.compile(r"Device [0-9]+:|acceleration for|Kokkos::Cuda|"
                     r"will use up to.*GPU")


def _stage_is_cpu(fam, logfile, procs):
    """GPU vs CPU per stage. PCFF: always GPU (mpi 1/4/8 = GPU-package/KOKKOS).
    UA: a stage is CPU only if mpi>=8 AND its stdout shows no GPU init."""
    if fam not in UA:
        return False
    if procs < 8:
        return False
    sf = logfile[:-4] + "_stdout.log"
    if os.path.exists(sf):
        try:
            if GPUINIT.search(open(sf, errors="ignore").read()):
                return False
        except OSError:
            pass
    return True


def harvest_run(run, fam):
    wall = gpu = cpu = cpu_core = core = 0.0
    nsteps = atoms = nlogs = 0
    cores = set()
    for f in glob.glob(os.path.join(DATA, run, "lammps", "**", "*.log"),
                       recursive=True):
        if any(b in f for b in BAD):
            continue
        try:
            txt = open(f, errors="ignore").read()
        except OSError:
            continue
        hit = False
        for m in LOOP.finditer(txt):
            t, p, s, a = (float(m.group(1)), int(m.group(2)),
                          int(m.group(3)), int(m.group(4)))
            if s == 0:
                continue
            t_h = t / 3600.0
            wall += t_h
            if _stage_is_cpu(fam, f, p):
                cpu += t_h
                cpu_core += t_h * p
            else:
                gpu += t_h
            core += t * p / 3600.0
            nsteps += s
            atoms = max(atoms, a)
            cores.add(p)
            hit = True
        if hit:
            nlogs += 1
    return dict(wall_h=wall, gpu_h=gpu, cpu_h=cpu, cpu_core_h=cpu_core,
                core_h=core, sim_ns=nsteps / 1e6, atoms=atoms,
                cores="/".join(map(str, sorted(cores))), n_logs=nlogs)


def main():
    os.makedirs(OUT, exist_ok=True)
    runs = sorted(d for d in os.listdir(DATA)
                  if os.path.isdir(os.path.join(DATA, d)) and RUN_RE.match(d))

    rows = []
    for run in runs:
        fam = FAM_RE.sub("", run)
        r = harvest_run(run, fam)
        if r["sim_ns"] == 0:          # no retained logs -> drop
            continue
        r.update(run=run, family=fam, ff_class=FF_CLASS[fam])
        rows.append(r)

    cols = ["run", "family", "ff_class", "atoms", "sim_ns", "wall_h",
            "gpu_h", "cpu_h", "cpu_core_h", "core_h", "cores", "n_logs"]
    with open(os.path.join(OUT, "compute_cost.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: (round(v, 2) if isinstance(v, float) else v)
                        for k, v in r.items()})

    # per-family aggregate (feeds SI tab:si_walltimes: Wall / GPU / CPU)
    fams = {}
    for r in rows:
        a = fams.setdefault(r["family"], dict(n=0, wall=0.0, gpu=0.0,
                                              cpu=0.0, core=0.0))
        a["n"] += 1
        a["wall"] += r["wall_h"]; a["gpu"] += r["gpu_h"]
        a["cpu"] += r["cpu_h"];  a["core"] += r["cpu_core_h"]
    print("\n=== PER-FAMILY (feeds SI tab:si_walltimes) — Wall/GPU/CPU h ===")
    tw = tg = tc = tcc = 0.0
    for fam in ("PE", "cis-PBD", "PLA", "PMMA", "PSU", "PVC", "PEEK",
                "PEG", "PS"):
        a = fams.get(fam)
        if not a:
            continue
        tw += a["wall"]; tg += a["gpu"]; tc += a["cpu"]; tcc += a["core"]
        print(f"  {fam:8s} n={a['n']}  wall {a['wall']:6.1f}  "
              f"gpu {a['gpu']:6.1f}  cpu {a['cpu']:5.1f}  "
              f"[{a['core']:5.0f} core-h]")
    print(f"  {'TOTAL':8s} n={sum(a['n'] for a in fams.values())}  "
          f"wall {tw:6.1f}  gpu {tg:6.1f}  cpu {tc:5.1f}  [{tcc:.0f} core-h]")

    # per-class aggregate
    classes = {}
    for r in rows:
        c = classes.setdefault(r["ff_class"], [])
        c.append(r)

    print(f"{'run':10s}{'ff':4s}{'atoms':>7s}{'sim_ns':>8s}{'wall_h':>8s}"
          f"{'core_h':>8s}  cores")
    for r in sorted(rows, key=lambda x: (x["ff_class"], x["family"])):
        print(f"{r['run']:10s}{r['ff_class']:4s}{r['atoms']:>7d}"
              f"{r['sim_ns']:>8.1f}{r['wall_h']:>8.1f}{r['core_h']:>8.1f}"
              f"  {r['cores']}")

    crows = []
    print("\n=== PER-CLASS (feeds tab:compute_cost) ===")
    tot_wall = tot_core = 0.0
    for cls in ("UA", "AA"):
        sub = classes.get(cls, [])
        if not sub:
            continue
        nrep = len(sub)
        wall = [r["wall_h"] for r in sub]
        core = [r["core_h"] for r in sub]
        ns = [r["sim_ns"] for r in sub]
        nsday = [r["sim_ns"] / (r["wall_h"] / 24.0) for r in sub if r["wall_h"]]
        tot_wall += sum(wall)
        tot_core += sum(core)
        agg = dict(
            ff_class=cls, label=FF_LABEL[cls], n_replicates=nrep,
            wall_h_min=round(min(wall), 1), wall_h_max=round(max(wall), 1),
            core_h_min=round(min(core), 1), core_h_max=round(max(core), 1),
            core_h_mean=round(sum(core) / nrep, 1),
            ns_per_day_min=round(min(nsday), 1),
            ns_per_day_max=round(max(nsday), 1))
        crows.append(agg)
        print(f"{FF_LABEL[cls]}: n={nrep} reps | "
              f"throughput {min(nsday):.0f}-{max(nsday):.0f} ns/day | "
              f"cost {min(core):.0f}-{max(core):.0f} core-h/rep "
              f"(mean {sum(core)/nrep:.0f}) | "
              f"wall {min(wall):.0f}-{max(wall):.0f} h/rep")
    with open(os.path.join(OUT, "compute_cost_class.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(crows[0].keys()))
        w.writeheader()
        w.writerows(crows)

    print(f"\nMeasured benchmark total ({len(rows)} logged runs): "
          f"{tot_wall:.0f} wall-h (~{tot_wall/24:.0f} d elapsed) "
          f"= {tot_core:.0f} CPU core-h (~{tot_core/24:.0f} core-days)")
    print("wrote csv/compute_cost.csv and csv/compute_cost_class.csv")


if __name__ == "__main__":
    main()
