#!/usr/bin/env python3
"""Emit LaTeX tables for SI S4, S5, S7 from manuscript/gen/out/{runs,regrade_continuous}.json."""
import json
from pathlib import Path

GEN = Path(__file__).resolve().parent / "out"
OUT = GEN / "si_snippets"
OUT.mkdir(exist_ok=True)
runs = json.loads((GEN / "runs.json").read_text())["runs"]
cont = json.loads((GEN / "regrade_continuous.json").read_text())["runs"]
FF = {"pcff": "PCFF", "trappe-ua": "TraPPE-UA"}
GATE = {"energy_drift": "energy drift", "energy_sem": "energy SEM", "n_eff_density": "density samples",
        "density_drift": "density drift"}


def esc(s):
    return str(s).replace("_", r"\_")


def name(run):
    return esc(run)


def f(x, nd=1):
    return "---" if x is None else f"{x:.{nd}f}"


def longtable(caption, label, cols, header, rows):
    ncol = len(header)
    h = " & ".join(rf"\textbf{{{c}}}" for c in header) + r" \\"
    return "\n".join([
        r"\scriptsize",
        rf"\begin{{longtable}}{{{cols}}}",
        rf"\caption{{{caption}}} \label{{{label}}} \\",
        r"\toprule", h, r"\midrule", r"\endfirsthead",
        r"\toprule", h, r"\midrule", r"\endhead",
        r"\bottomrule", r"\endfoot",
        *[" & ".join(r) + r" \\" for r in rows],
        r"\end{longtable}", r"\normalsize", ""])


# S4 per-run protocol
rows = []
for r in runs:
    p = r["protocol"]
    lad = "/".join(f"{x:g}" for x in (p.get("ladder_simulated_atm") or p["ladder_executed_atm"] or []))
    rows.append([name(r["run"]), FF.get(p["ff"], p["ff"]), f"{p['n_atoms']:,}".replace(",", "{,}"), str(p["dp"]),
                 str(p["n_chains"]), f(p["dt_fs"]), f(p["cutoff_A"]), f(p["T_equil_K"], 0),
                 f"{p['tg_rate_K_per_ns']} / {p['tg_t_step_K']}", lad, f"{p['emc_seed']} / {p['velocity_seed']}"])
(OUT / "s4.tex").write_text(longtable(
    r"Per-run protocol for the 21 runs. Atoms counts united-atom sites for PE. DP is the degree of polymerization, $n$ the chain count, $T_{\mathrm{equil}}$ the melt equilibration temperature, and the $T_g$ staircase is given as cooling rate (K/ns) / temperature step (K). The Murnaghan ladder lists the simulated pressures (atm), all of which enter the reported fit. Seeds are the EMC packing seed and the velocity seed.",
    "tab:si_per_run", "l l r r r r r r c l l",
    ["Run", "FF", "Atoms", "DP", "$n$", "d$t$ (fs)", "$r_c$ (\\AA)", "$T_{\\mathrm{equil}}$ (K)", "$T_g$ rate / step", "Murnaghan ladder (atm)", "Seeds"],
    rows))

# S5 disposition
rows = []
for r in runs:
    c = cont[r["run"]]

    def cell(st):
        v = c[st].get("verdict") or {}
        fail = [GATE.get(g, g.replace("_", " ")) for g in v.get("failing_binding_gates") or []]
        seg = c[st].get("n_segments") or 1
        basis = c[st].get("basis")
        note = ""
        if basis == "continuous_chain":
            note = f" ({seg} segments, continuous)"
        return (v.get("verdict") or "---") + (f" ({', '.join(fail)})" if fail else "") + note
    melt, cool = cell("equilibration"), cell("cooling")
    tg = r["tg"]["verdict"].replace("TG_", "").replace("_", " ").title()
    cause = f" ({r['tg']['cause'].replace('_', ' ')})" if r["tg"]["cause"] else ""
    props = "included" if (c["equilibration"].get("verdict") or {}).get("verdict") == "PASS" and \
        (c["cooling"].get("verdict") or {}).get("verdict") == "PASS" else "excluded"
    tgd = "included" if r["tg"]["reportable"] and (c["equilibration"].get("verdict") or {}).get("verdict") == "PASS" else "excluded"
    rows.append([name(r["run"]), melt, cool, tg + cause, props, tgd])
(OUT / "s5.tex").write_text(longtable(
    r"Per-run gate disposition under the frozen gate version, with restart continuations graded as one continuous run. Failing binding checks are in parentheses. 300~K properties (density, bulk modulus, structural diagnostics) require both gated cells to pass; $T_g$ requires a passing melt and a reportable fit.",
    "tab:si_disposition", "l p{3.4cm} p{3.4cm} p{2.6cm} l l",
    ["Run", "Melt cell", "Assessment cell (300 K)", "$T_g$ fit", "300 K properties", "$T_g$"], rows))

# S7 Tg
rows = []
for r in runs:
    t = r["tg"]
    rows.append([name(r["run"]), f(t["Tg_K"]), f(t["uncertainty_K"]), f(t["r_squared"], 4), t["fit_quality"].title(),
                 f(t["width_K"]), t["verdict"].replace("TG_", "").replace("_", " ").title()
                 + (f" ({t['cause'].replace('_', ' ')})" if t["cause"] else "")])
(OUT / "s7_tg.tex").write_text(longtable(
    r"Per-run $T_g$ from the smoothed-bilinear fit: uncertainty, $R^2$, fit quality, crossover half-width $c$, and reportability verdict.",
    "tab:si_tg", "l r r r l r l",
    ["Run", "$T_g$ (K)", "$\\pm$ (K)", "$R^2$", "Fit", "$c$ (K)", "Verdict"], rows))

# S7 density + K
rows = []
for r in runs:
    k, d = r["K"], r["density"]
    c = cont[r["run"]]
    def gate(stage):
        v = (c[stage].get("verdict") or {})
        out = v.get("verdict", "---")
        bad = v.get("failing_binding_gates") or []
        short = {"energy_drift": "E drift", "energy_sem": "E SEM", "density_drift": "$\\rho$ drift",
                 "density_sem": "$\\rho$ SEM", "n_eff_density": "$n_{\\mathrm{eff}}$",
                 "density_homogeneity": "homog.", "finite_size": "size"}
        return out + (" (" + ", ".join(short.get(x, x.replace("_", " ")) for x in bad) + ")" if bad else "")
    melt, cell = gate("equilibration"), gate("cooling")
    incl = "yes" if melt.startswith("PASS") and cell.startswith("PASS") else "no"
    rows.append([name(r["run"]), f(d["rho_300K"], 4), f(d["rho_melt"], 4), f"{f(k['K_GPa'], 3)} $\\pm$ {f(k['sem_GPa'], 3)}",
                 f(k["B0_prime"], 2), f(k["r_squared"], 4), str(k["n_points"]), f(k["fluctuation_K_GPa"], 2),
                 melt, cell, incl])
(OUT / "s7_rho_k.tex").write_text(longtable(
    r"Per-run density at 300~K and in the melt, Murnaghan bulk modulus, and the gate disposition of each cell under the frozen gate version: $K \pm$ fit standard error, $B_0'$, $R^2$, number of pressure points fitted, and the volume-fluctuation cross-check $K_{\mathrm{fluct}}$. The last three columns give the verdict of each gated cell under the frozen gate version and whether the run's 300~K properties are included. Two cells fail a binding thermodynamic check under the frozen regrade and are excluded.",
    "tab:si_rho_k", "l r r r r r r r l l c",
    ["Run", "$\\rho_{300}$", "$\\rho_{\\mathrm{melt}}$", "$K$ (GPa)", "$B_0'$", "$R^2$", "Pts", "$K_{\\mathrm{fluct}}$",
     "Melt", "300~K", "Incl."], rows))

# S7 structure
rows = []
for r in runs:
    s = r["structure_300K"]
    ed = ((cont[r["run"]]["cooling"].get("thermo") or {}).get("energy_drift") or {}).get("drift_pct")
    p = r["protocol"]
    seeds = f"{p['emc_seed']} / {p['velocity_seed']}" if p.get("emc_seed") else "---"
    rows.append([name(r["run"]), f(s["Rg_A"]), f(100 * s["Rg_cv"], 0) if s["Rg_cv"] is not None else "---",
                 f(s["Ree_A"]), f(s["msid_slope"], 2), f(s["p2"], 3),
                 f"{f(100 * s['rho_cv'], 0)} ({f(100 * s['rho_cv_floor'], 0)})" if s["rho_cv"] is not None else "---",
                 f(ed, 2), str(s["n_eff_density"]), seeds])
(OUT / "s7_struct.tex").write_text(longtable(
    r"Per-run structural and convergence diagnostics of the 300~K cell: mean radius of gyration and its coefficient of variation across chains, mean end-to-end distance, MSID slope, nematic order $P_2$, voxel density CV with its counting-noise floor, total-energy drift of the graded window (continuations read as one run), and independent density samples. Seeds are the EMC packing seed and the velocity seed.",
    "tab:si_struct", "l r r r r r r r r l",
    ["Run", "$\\langle R_g\\rangle$ (\\AA)", "$R_g$ CV (\\%)", "$\\langle R_{ee}\\rangle$ (\\AA)", "MSID", "$P_2$", "$\\rho$ CV (\\%) (floor)", "$E$ drift (\\%)", "$n_{\\mathrm{eff}}$", "Seeds (EMC / vel.)"], rows))
print("wrote", sorted(p.name for p in OUT.iterdir()))
