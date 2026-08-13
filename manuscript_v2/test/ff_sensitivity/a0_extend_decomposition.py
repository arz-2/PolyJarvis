#!/usr/bin/env python3
"""a0 — extend the melt/glass density decomposition to every glassy family.

The archive records `cooling_contraction.json` for only 3 usable families. The
decomposition needs two .data files and no MD, so every run whose glass and melt cells
survive can be assessed. This widens the evidence base for the question test 1 exists to
answer: is the density deficit in the FORCE FIELD (melt already low) or in the COOLING
PROTOCOL (melt fine, glass low)?

Two disciplines are enforced here that the archived records do not carry:

  - `extrapolation_reliable=False` is binding. PKTN (470 K span) and PSFO (400 K) exceed
    the tool's own 300 K limit, so their verdicts are reported UNCLASSIFIED rather than
    as evidence. A verdict computed outside its model's validity is not a weak result,
    it is not a result.
  - Rubbery families are excluded as INAPPLICABLE, not missing. PE, PEG and cis-PBD are
    above Tg at 300 K and never run an npt_prod300 stage, so they have no glass state to
    decompose. Their density deficits are real but belong to a different comparison.

Writes results/a0_decomposition.json and .md.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ASSESS = REPO / "mcp-servers/mcp-lammps-engine/analysis_scripts/assess_cooling_contraction.py"
DATA = REPO / "manuscript/data"
OUT = Path(__file__).resolve().parent / "results"

# Per-family inputs. exp_density and tg are the manuscript's own comparators
# (manuscript/property_comparison.md); T_equil is decided_params.T_equil_K.
# Kept explicit rather than re-derived so the numbers this produces are auditable
# against the table the paper already prints.
FAMILIES = {
    "PEEK": {"exp_density": 1.263, "tg_K": 418.0, "t_equil_K": 770.0, "glassy": True},
    "PMMA": {"exp_density": 1.190, "tg_K": 378.0, "t_equil_K": 550.0, "glassy": True},
    "PS":   {"exp_density": 1.050, "tg_K": 373.0, "t_equil_K": 550.0, "glassy": True},
    "PSU":  {"exp_density": 1.240, "tg_K": 463.0, "t_equil_K": 700.0, "glassy": True},
    "PVC":  {"exp_density": 1.385, "tg_K": 354.0, "t_equil_K": 530.0, "glassy": True},
    "PLA":  {"exp_density": 1.250, "tg_K": 331.0, "t_equil_K": 620.0, "glassy": True},
    # Rubbery at 300 K: no glass state, no npt_prod300 stage, decomposition inapplicable.
    "PE":       {"tg_K": 195.0, "glassy": False},
    "PEG":      {"tg_K": 206.0, "glassy": False},
    "cis-PBD":  {"tg_K": 174.0, "glassy": False},
}

RUN_RE = re.compile(r"^(cis-PBD|PEEK|PEG|PMMA|PSU|PVC|PLA|PS|PE)(\d+)$")


def family_of(run):
    m = RUN_RE.match(run)
    return m.group(1) if m else None


def cells(run):
    """(glass, melt) .data paths, or None where the stage never ran."""
    base = DATA / run / "lammps/equil"
    g = base / "npt_prod300/npt_prod300_out.data"
    m = base / "npt_production/npt_production_out.data"
    return (g if g.exists() else None), (m if m.exists() else None)


def assess(glass, melt, spec):
    cmd = [sys.executable, str(ASSESS),
           "--glass_data", str(glass),
           "--exp_density_gcm3", str(spec["exp_density"]),
           "--tg_K", str(spec["tg_K"]),
           "--t_equil_K", str(spec["t_equil_K"])]
    if melt:
        cmd += ["--melt_data", str(melt)]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if r.returncode != 0:
        return {"status": "failed", "error": (r.stderr or "")[-400:]}
    txt = r.stdout
    i, j = txt.find("{"), txt.rfind("}")
    if i < 0 or j < 0:
        return {"status": "failed", "error": "no JSON in stdout"}
    return json.loads(txt[i:j + 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default=str(OUT))
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = sorted(d.name for d in DATA.iterdir()
                  if d.is_dir() and RUN_RE.match(d.name))
    rows = []
    for run in runs:
        fam = family_of(run)
        spec = FAMILIES.get(fam)
        row = {"run": run, "family": fam}
        if spec is None:
            row["status"] = "UNKNOWN_FAMILY"
            rows.append(row)
            continue
        if not spec["glassy"]:
            row.update(status="INAPPLICABLE_RUBBERY", verdict=None,
                       note=(f"{fam} is rubbery at 300 K (Tg~{spec['tg_K']:.0f} K); no "
                             "npt_prod300 glass stage exists, so there is no melt/glass "
                             "split to compute. Any density deficit here is a rubbery "
                             "deficit and is not evidence in this comparison."))
            rows.append(row)
            continue

        glass, melt = cells(run)
        if glass is None:
            row.update(status="NO_GLASS_CELL", verdict=None)
            rows.append(row)
            continue

        a = assess(glass, melt, spec)
        if a.get("status") == "failed":
            row.update(status="ASSESS_FAILED", error=a.get("error"))
            rows.append(row)
            continue

        reliable = a.get("extrapolation_reliable", True)
        raw = a.get("verdict")
        row.update(
            status="OK",
            had_melt_cell=melt is not None,
            t_equil_K=spec["t_equil_K"],
            cooling_span_K=spec["t_equil_K"] - 300.0,
            exp_density_gcm3=spec["exp_density"],
            rho_melt=a.get("rho_melt"),
            rho_glass=a.get("rho_glass"),
            glass_density_gap_pct=a.get("glass_density_gap_pct"),
            melt_density_gap_pct=a.get("melt_density_gap_pct"),
            contraction_shortfall=a.get("contraction_shortfall"),
            extrapolation_reliable=reliable,
            verdict_raw=raw,
            # A3 applied: a verdict computed outside its model's validity is not evidence.
            verdict=raw if reliable else "UNCLASSIFIED_UNRELIABLE_EXTRAPOLATION",
        )
        rows.append(row)

    usable = [r for r in rows if r.get("status") == "OK" and r.get("extrapolation_reliable")]
    unrel = [r for r in rows if r.get("status") == "OK" and not r.get("extrapolation_reliable")]
    inapp = [r for r in rows if r.get("status") == "INAPPLICABLE_RUBBERY"]

    summary = {
        "runs_total": len(rows),
        "usable_reliable": len(usable),
        "usable_families": sorted({r["family"] for r in usable}),
        "unreliable_unclassified": len(unrel),
        "unreliable_families": sorted({r["family"] for r in unrel}),
        "inapplicable_rubbery": len(inapp),
        "inapplicable_families": sorted({r["family"] for r in inapp}),
        "note": ("melt_density_gap_pct here is still the alpha-extrapolated heuristic the "
                 "tool ships (generic 2.5e-4/6.0e-4). a1 replaces that target with "
                 "experimental rho(T) and is the number to classify on."),
    }

    (out_dir / "a0_decomposition.json").write_text(
        json.dumps({"summary": summary, "runs": rows}, indent=2))

    md = ["# a0 — melt/glass decomposition, all glassy families", "",
          f"Reliable: **{summary['usable_reliable']} runs** across "
          f"{len(summary['usable_families'])} families "
          f"({', '.join(summary['usable_families'])}).", "",
          f"Unclassified (extrapolation outside validity): {summary['unreliable_unclassified']} "
          f"({', '.join(summary['unreliable_families']) or 'none'}).", "",
          f"Inapplicable (rubbery, no glass state): {summary['inapplicable_rubbery']} "
          f"({', '.join(summary['inapplicable_families']) or 'none'}).", "",
          "| run | span K | rho_melt | rho_glass | glass gap % | melt gap % | shortfall | verdict |",
          "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r.get("status") != "OK":
            md.append(f"| {r['run']} | — | — | — | — | — | — | {r.get('status')} |")
            continue
        md.append("| {run} | {span:.0f} | {rm} | {rg} | {gg} | {mg} | {sf} | {v} |".format(
            run=r["run"], span=r["cooling_span_K"],
            rm=f"{r['rho_melt']:.4f}" if r.get("rho_melt") else "—",
            rg=f"{r['rho_glass']:.4f}" if r.get("rho_glass") else "—",
            gg=r.get("glass_density_gap_pct"), mg=r.get("melt_density_gap_pct"),
            sf=r.get("contraction_shortfall"), v=r.get("verdict")))
    md += ["", "**melt gap above is the alpha heuristic, not a measurement.** "
               "`assess_cooling_contraction.py` calls it \"only a routing heuristic\"; "
               "a1 recomputes the melt target from experimental rho(T)."]
    (out_dir / "a0_decomposition.md").write_text("\n".join(md) + "\n")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
