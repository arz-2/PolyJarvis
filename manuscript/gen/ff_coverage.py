#!/usr/bin/env python3
"""Force-field build coverage behind the class-prior justification (SI S2, `tab:si_ff_coverage`).

CPU only; never touches data/<run>/.

  1. trial builds  -- `forcefield.py capability` (a real EMC build) of every benchmark repeat
                      unit and PTFE under PCFF, OPLS-AA (2024), TraPPE-UA, and COMPASS. Results are
                      cached in out/ff_coverage/<system>.json; pass --force to rebuild.
  2. PCFF fluorine -- which pcff.frc sections carry a row with the fluorine type `f`, and whether
                      any Class II cross-term section does.
  3. PHAL sweep    -- per-field build outcomes for polyhalogenated repeat units in
                      docs/ff_coverage_sweep/{arm0,arm1}.jsonl (PoLyInfo trial builds).

Writes out/ff_coverage.json and out/si_snippets/ff_coverage.tex.
"""
from __future__ import annotations

import collections
import json
import re
import subprocess
import sys
from pathlib import Path

from replicates import REPO

OUT = Path(__file__).resolve().parent / "out"
CACHE = OUT / "ff_coverage"
FIELDS = ["pcff", "opls/2024/opls-aa", "trappe-ua", "compass"]
LABEL = {"pcff": "PCFF", "opls/2024/opls-aa": "OPLS-AA", "trappe-ua": "TraPPE-UA", "compass": "COMPASS"}
SYSTEMS = [  # (system, run whose plan gives the SMILES, class prior)
    ("PE", "PE_1", "trappe-ua"), ("PEG", "PEG_1", "pcff"), ("PLLA", "PLLA_1", "pcff"),
    ("aPS", "aPS_2", "pcff"), ("sPVC", "sPVC_2", "pcff"), ("PEEK", "PEEK_1", "pcff"),
    ("PSU", "PSU_1", "pcff"), ("PTFE", "PTFE_AI", "opls/2024/opls-aa"),
]
PCFF_FRC = Path("/home/arz2/emc/field/pcff/pcff.frc")
CROSS_SECTIONS = ("bond-bond", "bond-angle", "angle-angle", "torsion_3 ", "bond-torsion", "angle-torsion",
                  "torsion-torsion")


def smiles_of(run: str) -> str:
    return json.loads((REPO / "data" / run / "raw" / "run_plan.json").read_text())["smiles"]


def probe(system: str, smiles: str) -> dict:
    path = CACHE / f"{system}.json"
    if "--force" not in sys.argv and path.exists():
        doc = json.loads(path.read_text())
        if set(FIELDS) <= set(doc.get("fields", {})):
            return doc
    r = subprocess.run([sys.executable, str(REPO / "orchestration" / "scripts" / "forcefield.py"), "capability",
                        smiles, "--fields", ",".join(FIELDS)], capture_output=True, text=True, check=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_text(r.stdout)
    return json.loads(r.stdout)


def outcome(entry: dict) -> str:
    if entry.get("typing_evidence") == "built_cell":
        return "builds"
    err = entry.get("typing_error") or ""
    if "Missing rules" in err:
        return "no typing rule"
    if "Missing force field parameters" in err:
        return "missing parameters"
    if "not found" in err:
        return "element not typed"
    return "fails"


def pcff_fluorine() -> dict:
    sections, cur = collections.Counter(), None
    refs = {}
    for line in PCFF_FRC.read_text(errors="ignore").splitlines():
        if line.startswith("#"):
            cur = line.split()[0][1:]
            continue
        if cur and re.search(r"(^|\s)f(\s|$)", line):
            sections[cur] += 1
            m = re.match(r"\s*([\d.]+)\s+(\d+)\s", line)
            if m:
                refs.setdefault(cur, set()).add(f"v{m.group(1)} ref {m.group(2)}")
    cross = {s: n for s, n in sections.items() if any(c.strip() in s for c in CROSS_SECTIONS) and s != "torsion_3"}
    return {"sections_with_f": dict(sections), "versions_refs": {k: sorted(v) for k, v in refs.items()},
            "cross_term_rows_with_f": sum(cross.values())}


def phal_sweep() -> dict:
    rows = [json.loads(l) for f in ("arm0.jsonl", "arm1.jsonl")
            for l in (REPO / "docs" / "ff_coverage_sweep" / f).read_text().splitlines() if l.strip()]
    out = {}
    for field in ("opls/2024/opls-aa", "pcff"):
        sub = [r for r in rows if r["polymer_class"] == "PHAL" and r["field"] == field]
        out[field] = [{"smiles": r["smiles"], "built": bool(r.get("built")), "has_Cl": "Cl" in r["smiles"]} for r in sub]
    return out


def main() -> int:
    table = []
    for system, run, prior in SYSTEMS:
        doc = probe(system, smiles_of(run))
        table.append({"system": system, "prior": prior,
                      "outcomes": {f: outcome(doc["fields"][f]) for f in FIELDS}})
    doc = {"trial_builds": table, "pcff_fluorine": pcff_fluorine(), "phal_sweep": phal_sweep()}
    OUT.mkdir(exist_ok=True)
    (OUT / "ff_coverage.json").write_text(json.dumps(doc, indent=1))

    rows = []
    for t in table:
        cells = []
        for f in FIELDS:
            o = t["outcomes"][f]
            cells.append(rf"\textbf{{{o}}}" if f == t["prior"] else o)
        rows.append(" & ".join([t["system"], *cells]) + r" \\")
    tex = "\n".join([
        r"\begin{table}[H]", r"\centering",
        r"\caption{Trial EMC builds of each benchmark repeat unit and of PTFE under four force fields. "
        r"The class prior is in bold. ``No typing rule'': EMC has no atom-typing rule for a group; "
        r"``missing parameters'': typing succeeds but a bonded or increment row is absent; "
        r"``element not typed'': the field defines no type for an element. A build shows only that "
        r"the field can type the repeat unit, not that it is accurate for it.}",
        r"\label{tab:si_ff_coverage}", r"\small", r"\begin{tabular}{l l l l l}", r"\toprule",
        r"\textbf{System} & \textbf{PCFF} & \textbf{OPLS-AA} & \textbf{TraPPE-UA} & \textbf{COMPASS} \\",
        r"\midrule", *rows, r"\bottomrule", r"\end{tabular}", r"\end{table}", ""])
    (OUT / "si_snippets").mkdir(exist_ok=True)
    (OUT / "si_snippets" / "ff_coverage.tex").write_text(tex)
    print(json.dumps({"trial_builds": table, "pcff_cross_term_rows_with_f": doc["pcff_fluorine"]["cross_term_rows_with_f"],
                      "pcff_f_refs": doc["pcff_fluorine"]["versions_refs"],
                      "phal_sweep": {k: collections.Counter((r["has_Cl"], r["built"]) for r in v).most_common()
                                     for k, v in doc["phal_sweep"].items()}}, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
