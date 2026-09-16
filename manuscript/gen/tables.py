#!/usr/bin/env python3
"""Render the round-2 tables from gen/out/runs.json, mirroring the round-1 manuscript tables.

Every ensemble is given twice where a disposition choice changes it:
  - "accepted": all three accepted replicates;
  - "gate-pass": 300 K properties (density, K, structure) only from cells whose cooling gate
    PASSes under the frozen gate version; Tg only from TG_REPORTABLE fits.
Which one the manuscript reports is an author decision (DATA_TRACKER.md).

Usage: python3 manuscript/gen/tables.py  -> gen/out/tables.md
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean, stdev

OUT = Path(__file__).resolve().parent / "out"


def ms(xs, nd=1):
    xs = [x for x in xs if x is not None]
    if not xs:
        return "—", 0, None
    m = mean(xs)
    s = stdev(xs) if len(xs) > 1 else None
    txt = f"{m:.{nd}f}" + (f" ± {s:.{nd}f}" if s is not None else "")
    return txt, len(xs), m


def pct(sim, ref):
    return None if sim is None or ref is None else 100 * (sim - ref) / ref


def mark(ok):
    return "✓" if ok else "✗"


def fmt(x, nd=1, sign=False):
    if x is None:
        return "—"
    return f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


REFS = json.loads((Path(__file__).resolve().parent / "references.json").read_text())


def ref_values(system: str, prop: str):
    """Sorted admissible experimental values, or None when the property is ungraded."""
    node = REFS["systems"][system][prop]
    if "ungraded" in node:
        return None
    return sorted(x["v"] for x in node["include"])


def ref_text(vals, nd):
    if vals is None:
        return "ungraded"
    lo, hi = vals[0], vals[-1]
    return f"{lo:.{nd}f}" if lo == hi else f"{lo:.{nd}f}–{hi:.{nd}f} (n={len(vals)})"


def grade(sim, vals, prop):
    """User rule: single value -> tolerance around it; band -> inside, or within tolerance of the
    nearer edge. Returns (deviation from the value/nearest edge in the criterion's unit, pass)."""
    if sim is None or vals is None:
        return None, None
    lo, hi = vals[0], vals[-1]
    tol = REFS["tolerance"][prop]
    if lo <= sim <= hi and lo != hi:
        return 0.0, True
    edge = lo if sim < lo else hi
    if "abs" in tol:
        dev = sim - edge
        return dev, abs(dev) <= tol["abs"]
    dev = 100.0 * (sim - edge) / edge
    return dev, abs(dev) <= 100.0 * tol["rel"]


def main() -> None:
    D = json.loads((OUT / "runs.json").read_text())
    runs = D["runs"]
    systems = list(REFS["systems"])
    by = {s: [r for r in runs if r["system"] == s] for s in systems}
    # Inclusion follows the continuous-chain regrade (gen/regrade_continuous.py): a run's 300 K
    # properties need both gated cells to PASS; its Tg needs the melt to PASS and a reportable fit.
    cont = json.loads((OUT / "regrade_continuous.json").read_text())["runs"]
    verdict = lambda r, st: (cont[r["run"]][st].get("verdict") or {}).get("verdict")
    cool_pass = lambda r: verdict(r, "equilibration") == "PASS" and verdict(r, "cooling") == "PASS"
    tg_ok = lambda r: verdict(r, "equilibration") == "PASS" and bool(r["tg"]["reportable"])
    L: list[str] = []
    w = L.append

    # ---------------- Table 2: references
    w("## Table 2 — Benchmark systems and experimental references\n")
    w("Single value when one admissible measurement exists, else the band [min–max] over n values "
      "(sources and exclusions: gen/references.json).\n")
    w("| Polymer | FF | Host | Tg (K) | ρ (g/cm³) | K_T (GPa) |")
    w("|---|---|---|---|---|---|")
    for s in systems:
        rs = by[s]
        pend = " (pending search)" if "_pending" in REFS["systems"][s] else ""
        w(f"| {s}{pend} | {rs[0]['protocol']['ff']} | {rs[0]['host']} | {ref_text(ref_values(s, 'tg_K'), 1)} | "
          f"{ref_text(ref_values(s, 'density'), 4)} | {ref_text(ref_values(s, 'K_GPa'), 3)} |")

    # ---------------- Density
    w("\n## §3.1 — Density at 300 K\n")
    w("Gate-passing cells only. Δ% is measured from the single value, or from the nearer band edge (0 inside the band).\n")
    w("| Polymer | Exp. | ρ mean ± s.d. (n) | Δ% | ±5% | Excluded (gate) |")
    w("|---|---|---|---|---|---|")
    dens = {}
    for s in systems:
        vals = ref_values(s, "density")
        g_txt, g_n, g_m = ms([r["density"]["rho_300K"] for r in by[s] if cool_pass(r)], 4)
        dev, ok = grade(g_m, vals, "density")
        dens[s] = (dev, ok)
        excl = ", ".join(r["run"] for r in by[s] if not cool_pass(r)) or "—"
        w(f"| {s} | {ref_text(vals, 4)} | {g_txt} ({g_n}) | {fmt(dev, 1, True)} | {mark(ok) if ok is not None else '—'} | {excl} |")
    w("\nMelt-vs-glass decomposition (glassy runs with cooling_contraction.json):\n")
    w("| Run | ρ_melt (T) | ρ_300K | expected contraction | actual | shortfall | verdict |")
    w("|---|---|---|---|---|---|---|")
    for r in runs:
        c = r["density"]["contraction"]
        if c:
            w(f"| {r['run']} | {fmt(r['density']['rho_melt'], 4)} ({fmt(r['density']['T_melt_K'], 0)} K) | "
              f"{fmt(r['density']['rho_300K'], 4)} | {c['expected_contraction']} | {c['actual_contraction']} | "
              f"{c['contraction_shortfall']} | {c['verdict']} |")
    pair = D.get("peg_size_pair") or []
    if len(pair) == 2 and all(p["B0_GPa"] for p in pair):
        w("\nPEG system size (earlier-protocol COMPASS cells, DP 100; data/peg_size_v1):\n")
        w("| Run | Chains | B0 (GPa) | R² |")
        w("|---|---|---|---|")
        for p in pair:
            w(f"| {p['run']} | {p['n_chains']} | {p['B0_GPa']:.4f} ± {p['B0_sem_GPa']:.4f} | {p['r_squared']} |")
        w(f"\nB0 change on doubling chain count: {100 * (pair[1]['B0_GPa'] / pair[0]['B0_GPa'] - 1):+.1f}%")

    # ---------------- Tg
    w("\n## §3.2 — Glass transition temperature\n")
    w("Means over reportable fits only (TG_REVIEW runs excluded); excluded runs listed per row.\n")
    w("| Polymer | Exp. | Tg mean ± s.d. (n) | ΔTg (K) | ±50 K | Excluded (TG_REVIEW) |")
    w("|---|---|---|---|---|---|")
    tgd = {}
    for s in systems:
        vals = ref_values(s, "tg_K")
        g_txt, g_n, g_m = ms([r["tg"]["Tg_K"] for r in by[s] if tg_ok(r)])
        dev, ok = grade(g_m, vals, "tg_K")
        tgd[s] = (dev, ok)
        excl = ", ".join(f"{r['run']} ({r['tg']['Tg_K']})" for r in by[s] if not tg_ok(r)) or "—"
        w(f"| {s} | {ref_text(vals, 1)} | {g_txt} ({g_n}) | {fmt(dev, 1, True)} | {mark(ok) if ok is not None else '—'} | {excl} |")
    devs = [abs(tgd[s][0]) for s in systems if tgd[s][0] is not None]
    w(f"\nMean |ΔTg| from value or nearest band edge ({len(devs)} systems): {mean(devs):.1f} K")

    # ---------------- Tg sensitivity
    w("\n## §3.3 — Tg sensitivity (predeclared rule: sensitive iff |ΔTg| > pooled within-system replicate s.d.)\n")
    pooled = {}
    for label, filt in (("reportable only", tg_ok),):
        num = den = 0.0
        for s in systems:
            xs = [r["tg"]["Tg_K"] for r in by[s] if filt(r)]
            if len(xs) > 1:
                num += (len(xs) - 1) * stdev(xs) ** 2
                den += len(xs) - 1
        pooled[label] = math.sqrt(num / den)
        w(f"- Pooled within-system s.d. ({label}): **{pooled[label]:.1f} K** (dof {den:.0f})")
    anchor_tg = {r["run"]: r["tg"]["Tg_K"] for r in runs}
    w("\n| Leg | Axis | Rate (K/ns) | Step (K) | Tg (K) | ± | ΔTg vs anchor | Verdict | Sensitive? |")
    w("|---|---|---|---|---|---|---|---|---|")
    for g in D["tg_legs"]:
        base = anchor_tg[g["anchor"]]
        dt = None if g["Tg_K"] is None else g["Tg_K"] - base
        sens = "—" if dt is None or not g["reportable"] else \
            ("yes" if abs(dt) > pooled["reportable only"] else "no")
        v = g["verdict"] + (f" ({g['cause']}, gap {g['method_gap_K']} K)" if g["cause"] else "")
        w(f"| {g['leg']} | {g['axis']} | {g['tg_rate_K_per_ns']} | {g['tg_t_step_K']} | {fmt(g['Tg_K'])} | "
          f"{fmt(g['uncertainty_K'])} | {fmt(dt, 1, True)} vs {base} | {v} | {sens} |")
    w("\nAnchors: PE_1 at 40 K/ns, 20 K step; PLLA_1 at 100 K/ns, 20 K step. Equilibration-duration and fit-procedure axes: no legs run.")

    # ---------------- K
    w("\n## §3.4 — Bulk modulus at 300 K (Murnaghan)\n")
    w("| Polymer | Exp. K_T | K mean ± s.d. (n) | Δ% | ±30% | Excluded (gate) |")
    w("|---|---|---|---|---|---|")
    kd = {}
    for s in systems:
        vals = ref_values(s, "K_GPa")
        g_txt, g_n, g_m = ms([r["K"]["K_GPa"] for r in by[s] if cool_pass(r)], 2)
        dev, ok = grade(g_m, vals, "K_GPa")
        kd[s] = (dev, ok)
        excl = ", ".join(r["run"] for r in by[s] if not cool_pass(r)) or "—"
        w(f"| {s} | {ref_text(vals, 3)} | {g_txt} ({g_n}) | {fmt(dev, 1, True)} | {mark(ok) if ok is not None else '—'} | {excl} |")
    divs = [abs(pct(r["K"]["fluctuation_K_GPa"], r["K"]["K_GPa"])) for r in runs if r["K"]["fluctuation_K_GPa"]]
    w(f"\nMurnaghan vs volume-fluctuation K: per-run |divergence| median {sorted(divs)[len(divs)//2]:.1f}%, max {max(divs):.1f}%.")

    # ---------------- Table 4 structure
    w("\n## Table 4 — Equilibration and conformational diagnostics at 300 K (gate-passing cells; n in first column)\n")
    w("| Polymer (n) | ⟨Rg⟩ (Å) | Rg CV (%) | MSID slope | P2 | ρ CV (%) (floor) | E drift (%) |")
    w("|---|---|---|---|---|---|---|")
    for s in systems:
        rs = [r for r in by[s] if cool_pass(r)]
        g = lambda k: [r["structure_300K"][k] for r in rs]
        rg = ms(g("Rg_A"))[0]
        cv = ms([x * 100 for x in g("Rg_cv")], 0)[0].split(" ±")[0]
        msid = ms(g("msid_slope"), 2)[0]
        p2 = ms(g("p2"), 3)[0]
        rcv = ms([x * 100 for x in g("rho_cv")], 0)[0].split(" ±")[0]
        floor = ms([x * 100 for x in g("rho_cv_floor")], 0)[0].split(" ±")[0]
        # Energy drift from the continuous-chain regrade (base + continuation read as one run).
        ed = ms([(cont[r["run"]]["cooling"].get("thermo") or {}).get("energy_drift", {}).get("drift_pct")
                 for r in rs], 2)[0]
        w(f"| {s} ({len(rs)}) | {rg} | {cv} | {msid} | {p2} | {rcv} ({floor}) | {ed} |")
    w("\nE drift is the nominal total-energy drift of the 300 K window; it binds only when > 1% AND p < 0.01 "
      "(e.g. sPVC_1 4.48%, p = 0.054 → pass).")
    w("\nRDFs (old Figure 6): no RDF output exists for any round-2 run.")

    # ---------------- Table 5 summary
    w("\n## Table 5 — Validation summary (replicate means)\n")
    head = "| Property (gate) | " + " | ".join(systems) + " |"
    w(head)
    w("|" + "---|" * (len(systems) + 1))
    for label, d, unit in (("ρ (±5%)", dens, "%"), ("Tg (±50 K)", tgd, " K"), ("K (±30%)", kd, "%")):
        w(f"| {label} | " + " | ".join(
            "—" if d[s][1] is None else f"{mark(d[s][1])} {d[s][0]:+.1f}" for s in systems) + " |")
    counts = {k: (sum(1 for s in systems if d[s][1]), sum(1 for s in systems if d[s][1] is not None))
              for k, d in (("density", dens), ("Tg", tgd), ("K", kd))}
    tot = (sum(c[0] for c in counts.values()), sum(c[1] for c in counts.values()))
    w(f"\nScorecard: {tot[0]} of {tot[1]} — " + ", ".join(f"{k} {c[0]}/{c[1]}" for k, c in counts.items()))
    if any("_pending" in REFS["systems"][s] for s in systems):
        w("\nsPVC references are provisional (commercial PVC) until the syndiotactic search lands.")

    # ---------------- Table 6 cost
    w("\n## Table 6 — Computational cost per replicate (engine attempt time, all attempts incl. failed/superseded)\n")
    w("| Polymer | FF | Host | GPU-stage h per replicate (range) | of which failed/superseded (sum) | Total GPU-stage h |")
    w("|---|---|---|---|---|---|")
    tot_host: dict = {}
    for s in systems:
        rs = by[s]
        hs = [r["cost"]["gpu_stage_h"] for r in rs]
        tot_host[rs[0]["host"]] = tot_host.get(rs[0]["host"], 0) + sum(hs)
        w(f"| {s} | {rs[0]['protocol']['ff']} | {rs[0]['host']} | {min(hs):.1f}–{max(hs):.1f} | "
          f"{sum(r['cost']['failed_or_superseded_gpu_h'] for r in rs):.1f} | {sum(hs):.1f} |")
    w("\n" + "; ".join(f"{h}: {v:.0f} GPU-stage h" for h, v in tot_host.items()) +
      " (hosts not pooled: RTX 6000 vs A800 throughput differ; overlapping runs on one card not deconvolved).")

    # ---------------- SI per-run tables
    w("\n## SI S4 — Per-run protocol\n")
    w("| Run | FF | Atoms | DP | n | dt (fs) | cutoff (Å) | T_equil (K) | Tg rate (K/ns) / step (K) | Murnaghan ladder executed (atm) | emc / velocity seed |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        p = r["protocol"]
        lad = " / ".join(f"{x:g}" for x in (p["ladder_executed_atm"] or []))
        w(f"| {r['run']} | {p['ff']} | {p['n_atoms']} | {p['dp']} | {p['n_chains']} | {p['dt_fs']} | {p['cutoff_A']} | "
          f"{p['T_equil_K']} | {p['tg_rate_K_per_ns']} / {p['tg_t_step_K']} | {lad} | {p['emc_seed']} / {p['velocity_seed']} |")

    w("\n## SI S7 — Per-run Tg\n")
    w("| Run | Tg (K) | ± (K) | R² | fit | width c (K) | verdict (cause) | glassy at 300 K |")
    w("|---|---|---|---|---|---|---|---|")
    for r in runs:
        t = r["tg"]
        w(f"| {r['run']} | {fmt(t['Tg_K'])} | {fmt(t['uncertainty_K'])} | {fmt(t['r_squared'], 4)} | {t['fit_quality']} | "
          f"{fmt(t['width_K'])} | {t['verdict']}{' (' + t['cause'] + ')' if t['cause'] else ''} | {t['is_glassy_at_300K']} |")

    w("\n## SI S7 — Per-run density and bulk modulus\n")
    w("| Run | ρ 300 K | ρ melt | K (GPa) ± sem | B0' | R² | points | K_fluct (GPa) | LOO max ΔB0 (%) | ladder convergence |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        k, d = r["K"], r["density"]
        w(f"| {r['run']} | {fmt(d['rho_300K'], 4)} | {fmt(d['rho_melt'], 4)} | {fmt(k['K_GPa'], 3)} ± {fmt(k['sem_GPa'], 3)} | "
          f"{fmt(k['B0_prime'], 2)} | {fmt(k['r_squared'], 4)} | {k['n_points']} | {fmt(k['fluctuation_K_GPa'], 2)} | "
          f"{fmt(k['loo_max_dB0_pct'], 1)} | {k['convergence_verdict']} |")

    w("\n## SI S5 — Per-run gate disposition (frozen gate version)\n")
    w("| Run | Melt: live → old → frozen | Cooling: live → old → frozen | Tg verdict | K ladder | Remedies | Agent calls (actions) | Operator | Critic ran | 300 K props | Tg |")
    w("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        gm, gc, iv, pl = r["gates"]["melt"], r["gates"]["cooling"], r["interventions"], r["planning"]
        fl = lambda g: f"{g['live']} → {g['old']} → **{g['new']}**" + (f" ({', '.join(g['new_failing'])})" if g["new_failing"] else "")
        op = ", ".join([f"accepted {k}" for k in iv["operator_acceptance"]] +
                       ([f"{iv['operator_interventions']} repair(s)"] if iv["operator_interventions"] else [])) or "—"
        acts = ", ".join(a or "?" for a in iv["agent_actions"])
        w(f"| {r['run']} | {fl(gm)} | {fl(gc)} | {r['tg']['verdict']} | {r['K']['convergence_verdict']} | {iv['remedies']} | "
          f"{iv['agent_escalations']}{' (' + acts + ')' if acts else ''}{' +' + str(iv['escalations_archived']) + ' archived' if iv['escalations_archived'] else ''} | {op} | "
          f"{'yes' if pl['critic_ran'] else 'no'} | "
          f"{'include' if cool_pass(r) else 'EXCLUDE'} | {'include' if tg_ok(r) else 'EXCLUDE'} |")

    (OUT / "tables.md").write_text("\n".join(L) + "\n")
    print(f"wrote {OUT / 'tables.md'}")


if __name__ == "__main__":
    main()
