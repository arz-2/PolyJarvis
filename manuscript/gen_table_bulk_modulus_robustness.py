#!/usr/bin/env python3
"""Bulk-modulus statistical-robustness table.

Reports autocorrelation times, effective sample sizes, block-averaged
uncertainties, and method/barostat sensitivity for the NPT volume-fluctuation
bulk modulus, computed from data already on disk:

  - Volume-fluctuation K   manuscript/data/<RUN>/raw/bulk_modulus.json (method=volume_fluctuation)
                           + manuscript/data/<RUN>/raw/volume_timeseries.csv (raw V(t))
  - Murnaghan EOS K        manuscript/data/<RUN>/raw/bulk_modulus_murnaghan.json  (independent;
                           5-pressure NPT series, depends on <V> not Var(V))
  - Uniaxial deformation K manuscript/data/<RUN>/raw/deform*/bulk_modulus_deform.json (NVT, no barostat)

IMPORTANT: the pipeline's stored `tau_eff_frames` / `n_effective_samples` are
UNRELIABLE (they underestimate tau by 5-25x; e.g. cis-PBD3 stores N_eff=902 but the
integrated ACF of V(t) gives N_eff=36). We therefore recompute the integrated
autocorrelation time directly from volume_timeseries.csv here and report THAT.

Outputs:
  manuscript/csv/bulk_modulus_robustness.csv      (per-run)
  manuscript/csv/bulk_modulus_robustness_family.csv (per-family means +/- s.d.)
"""
import csv
import glob
import json
import os
import re

import numpy as np

DATA = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "csv")
FAMILIES = ["cis-PBD", "PE", "PEG", "PLA", "PMMA", "PS", "PSU", "PVC", "PEEK"]
RUN_RE = re.compile(r"^(?:cis-PBD|PE|PEG|PLA|PMMA|PS|PSU|PVC|PEEK)\d+$")
FAM_RE = re.compile(r"\d+$")


def integrated_act(x):
    """Integrated autocorrelation time (frames) by summing the ACF to first
    zero crossing; effective sample size N_eff = N / tau."""
    x = np.asarray(x, float)
    x = x - x.mean()
    n = len(x)
    var = np.dot(x, x) / n
    if var == 0:
        return 1.0, float(n)
    tau = 1.0
    for k in range(1, n // 2):
        c = np.dot(x[:-k], x[k:]) / ((n - k) * var)
        if c <= 0:
            break
        tau += 2.0 * c
    return tau, n / tau


def load(run):
    rec = dict(run=run, family=FAM_RE.sub("", run))
    # --- volume fluctuation: prefer the dedicated fluctuation file (e.g. PS1, whose
    #     generic bulk_modulus.json holds the withdrawn Born run), else the generic
    #     file when it is itself a volume_fluctuation result ---
    pf = os.path.join(DATA, run, "raw", "bulk_modulus_fluctuation.json")
    p = os.path.join(DATA, run, "raw", "bulk_modulus.json")
    if os.path.exists(pf):
        j = json.load(open(pf))
        rec["K_fluc_GPa"] = j.get("bulk_modulus_GPa")
        rec["K_fluc_blockSEM_GPa"] = j.get("bulk_modulus_sem_GPa")
    elif os.path.exists(p):
        j = json.load(open(p))
        if j.get("method") == "volume_fluctuation":
            rec["K_fluc_GPa"] = j.get("bulk_modulus_GPa")
            rec["K_fluc_blockSEM_GPa"] = j.get("bulk_modulus_sem_GPa")
    ts = os.path.join(DATA, run, "raw", "volume_timeseries.csv")
    if os.path.exists(ts) and rec.get("K_fluc_GPa") is not None:
        d = np.genfromtxt(ts, delimiter=",", names=True)
        step, V = d["step"], d["volume"]
        half = len(V) // 2
        Vp = V[half:]
        if Vp.std() > 0:            # skip Born/NVT constant-volume series (e.g. PS1) — no ACF
            tau, neff = integrated_act(Vp)
            thermo = float(np.median(np.diff(step)))            # MD steps / frame
            rec["thermo_steps"] = thermo
            rec["prod_ns"] = (step[-1] - step[half]) * 1e-6     # dt=1 fs -> ns
            rec["tau_V_ps"] = tau * thermo * 1e-3               # frames -> ps (dt=1 fs)
            rec["n_eff"] = neff
            rec["stat_floor_pct"] = np.sqrt(2.0 / neff) * 100   # sigma(K)/K from Var(V) estimator
            rec["V_cv_pct"] = 100 * Vp.std() / Vp.mean()
    # --- Murnaghan EOS (independent) ---
    pm = os.path.join(DATA, run, "raw", "bulk_modulus_murnaghan.json")
    if os.path.exists(pm):
        jm = json.load(open(pm))
        rec["K_murn_GPa"] = jm.get("bulk_modulus_GPa")
        rec["K_murn_SEM_GPa"] = jm.get("bulk_modulus_sem_GPa")
        rec["murn_r2"] = jm.get("r_squared")
        rec["murn_B0p"] = jm.get("B0_prime")
        # validity gate: fit_converged AND R2>=0.99 AND B0' in [4,20]
        rec["murn_gate_pass"] = bool(
            jm.get("fit_converged", False)
            and (rec["murn_r2"] or 0) >= 0.99
            and rec["murn_B0p"] is not None
            and 4.0 <= rec["murn_B0p"] <= 20.0)
    # --- deformation (NVT, no barostat); average available axes ---
    dks = [json.load(open(f)).get("K_GPa")
           for f in glob.glob(os.path.join(DATA, run, "raw", "deform*", "bulk_modulus_deform.json"))]
    single = os.path.join(DATA, run, "raw", "bulk_modulus_deform.json")
    if not dks and os.path.exists(single):
        dks = [json.load(open(single)).get("K_GPa")]
    dks = [v for v in dks if v is not None]
    if dks:
        rec["K_deform_GPa"] = float(np.mean(dks))
    # --- headline: uniform gated Murnaghan (2026-07-01). Use the Murnaghan K when its
    #     fit passes the validity gate; otherwise fall back to volume fluctuation (flagged).
    #     Deformation is a finite-rate lower bound and is NEVER the headline. ---
    if rec.get("murn_gate_pass"):
        rec["K_headline_GPa"] = rec.get("K_murn_GPa")
        rec["headline_method"] = "murnaghan_gated"
    elif rec.get("K_fluc_GPa") is not None:
        rec["K_headline_GPa"] = rec.get("K_fluc_GPa")
        rec["headline_method"] = "fluctuation_fallback"
    elif rec.get("K_murn_GPa") is not None:
        # Murnaghan present but gate-failed and no fluctuation available
        rec["K_headline_GPa"] = rec.get("K_murn_GPa")
        rec["headline_method"] = "murnaghan_ungated"
    return rec


def main():
    runs = sorted(d for d in os.listdir(DATA) if RUN_RE.match(d))
    recs = [load(r) for r in runs]
    os.makedirs(OUT, exist_ok=True)

    cols = ["run", "family", "prod_ns", "thermo_steps", "tau_V_ps", "n_eff",
            "stat_floor_pct", "V_cv_pct", "K_fluc_GPa", "K_fluc_blockSEM_GPa",
            "K_murn_GPa", "K_murn_SEM_GPa", "murn_r2", "murn_B0p", "murn_gate_pass",
            "K_deform_GPa", "K_headline_GPa", "headline_method"]
    with open(os.path.join(OUT, "bulk_modulus_robustness.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in recs:
            w.writerow({k: (round(v, 4) if isinstance(v, float) else v)
                        for k, v in r.items()})

    # per-family
    def ms(vals):
        vals = [v for v in vals if v is not None]
        if not vals:
            return (None, None, 0)
        return (float(np.mean(vals)), float(np.std(vals)), len(vals))

    frows = []
    for fam in FAMILIES:
        sub = [r for r in recs if r["family"] == fam]
        fl_m, fl_s, fl_n = ms([r.get("K_fluc_GPa") for r in sub])
        mu_m, mu_s, mu_n = ms([r.get("K_murn_GPa") for r in sub])
        de_m, de_s, de_n = ms([r.get("K_deform_GPa") for r in sub])
        hd_m, hd_s, hd_n = ms([r.get("K_headline_GPa") for r in sub])
        neffs = [r.get("n_eff") for r in sub if r.get("n_eff") is not None]
        prods = [r.get("prod_ns") for r in sub if r.get("prod_ns") is not None]
        dev = (abs(fl_m - mu_m) / mu_m * 100) if (fl_m and mu_m) else None
        frows.append(dict(
            family=fam, K_fluc_mean=fl_m, K_fluc_sd=fl_s, n_fluc=fl_n,
            K_murn_mean=mu_m, K_murn_sd=mu_s, n_murn=mu_n,
            K_deform_mean=de_m, n_deform=de_n,
            K_headline_mean=hd_m, K_headline_sd=hd_s, n_headline=hd_n,
            fluc_vs_murn_pct=dev,
            min_n_eff=(min(neffs) if neffs else None),
            prod_ns_min=(min(prods) if prods else None),
            prod_ns_max=(max(prods) if prods else None)))
    with open(os.path.join(OUT, "bulk_modulus_robustness_family.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(frows[0].keys()))
        w.writeheader()
        for r in frows:
            w.writerow({k: (round(v, 3) if isinstance(v, float) else v)
                        for k, v in r.items()})

    print("wrote csv/bulk_modulus_robustness.csv and _family.csv")
    hdr = f"{'fam':9s}{'Kfluc':>13s}{'Kmurn':>13s}{'Khead':>13s}{'dev%':>6s}{'Kdef':>6s}{'minNeff':>8s}"
    print(hdr)
    for r in frows:
        def cell(m, s, n):
            return f"{m:.2f}±{s:.2f}(n{n})" if m is not None else "-"
        print(f"{r['family']:9s}"
              f"{cell(r['K_fluc_mean'], r['K_fluc_sd'], r['n_fluc']):>13s}"
              f"{cell(r['K_murn_mean'], r['K_murn_sd'], r['n_murn']):>13s}"
              f"{cell(r['K_headline_mean'], r['K_headline_sd'], r['n_headline']):>13s}"
              f"{r['fluc_vs_murn_pct']:>6.1f}" if r['fluc_vs_murn_pct'] is not None else f"{r['family']:9s}",
              end="")
        print(f"{(r['K_deform_mean'] if r['K_deform_mean'] else 0):>6.2f}"
              f"{(r['min_n_eff'] if r['min_n_eff'] else 0):>8.0f}")


if __name__ == "__main__":
    main()
