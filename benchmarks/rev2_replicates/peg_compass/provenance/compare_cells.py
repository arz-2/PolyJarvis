"""Step 4: compare each PEG_COMPASS_<i> build cell with PEG_<i>'s accepted PCFF cell.

Usage: python3 compare_cells.py 1 [2 3]
"""
import collections
import glob
import json
import re
import sys
from pathlib import Path

REPO = Path("/home/alexzhao/PolyJarvis")


def accepted_build_dir(run: str) -> Path:
    st = json.loads((REPO / "data" / run / "workflow_state.json").read_text())
    rec = st["stages"]["build"]
    att = rec.get("accepted_attempt") or next(
        (a.get("attempt_id") for a in reversed(rec.get("attempts", [])) if a.get("status") == "accepted"), None)
    if isinstance(att, dict):
        att = att.get("attempt_id")
    return REPO / "data" / run / "attempts" / "build" / str(att) / "work" / "cell"


def parse_data(path: Path) -> dict:
    lines = path.read_text().splitlines()
    out = {"counts": {}, "box": {}, "masses": {}, "atoms": {}, "sections": []}
    i = 0
    while i < len(lines):
        s = lines[i].split("#")[0].strip()
        m = re.match(r"^(\d+)\s+(atoms|bonds|angles|dihedrals|impropers|atom types|bond types|angle types|dihedral types|improper types)$", s)
        if m:
            out["counts"][m.group(2)] = int(m.group(1))
        m = re.match(r"^(\S+)\s+(\S+)\s+(xlo xhi|ylo yhi|zlo zhi|xy xz yz)$", s) or re.match(r"^(\S+)\s+(\S+)\s+(\S+)\s+(xy xz yz)$", s)
        if m and m.group(m.lastindex) != "xy xz yz":
            out["box"][m.group(3)] = (float(m.group(1)), float(m.group(2)))
        head = lines[i].strip()
        if head and re.match(r"^[A-Z][A-Za-z ]+(\s+#.*)?$", head) and not re.match(r"^\d", head):
            name = head.split("#")[0].strip()
            out["sections"].append(name)
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            while i < len(lines) and lines[i].strip() and re.match(r"^\s*-?\d", lines[i]):
                f = lines[i].split("#")
                tok = f[0].split()
                if name == "Masses":
                    out["masses"][int(tok[0])] = f[1].strip() if len(f) > 1 else tok[0]
                elif name == "Atoms":
                    # full: id mol type q x y z [ix iy iz]
                    out["atoms"][int(tok[0])] = (int(tok[1]), int(tok[2]), float(tok[3]),
                                                 float(tok[4]), float(tok[5]), float(tok[6]))
                i += 1
            continue
        i += 1
    return out


def seed(cell_dir: Path):
    m = re.search(r"-seed=(\d+)", (cell_dir / "emc_build.log").read_text())
    return int(m.group(1)) if m else None


def field_named(cell_dir: Path):
    log = (cell_dir / "emc_build.log").read_text()
    m = re.search(r"-field=(\S+)", log)
    return m.group(1) if m else None


def compare(i: int) -> dict:
    p_dir, c_dir = accepted_build_dir(f"PEG_{i}"), accepted_build_dir(f"PEG_COMPASS_{i}")
    P, C = parse_data(p_dir / "cell.data"), parse_data(c_dir / "cell.data")
    r = {"pair": f"PEG_{i} (pcff) vs PEG_COMPASS_{i} (compass)",
         "pcff_cell": str(p_dir / "cell.data"), "compass_cell": str(c_dir / "cell.data")}
    keys = ("atoms", "bonds", "angles", "dihedrals", "impropers")
    r["counts"] = {k: (P["counts"].get(k), C["counts"].get(k)) for k in keys}
    r["type_counts"] = {k: (P["counts"].get(k), C["counts"].get(k))
                        for k in ("atom types", "bond types", "angle types", "dihedral types", "improper types")}
    r["box"] = {k: (P["box"].get(k), C["box"].get(k)) for k in ("xlo xhi", "ylo yhi", "zlo zhi")}
    r["same_atoms_bonds_box"] = (r["counts"]["atoms"][0] == r["counts"]["atoms"][1]
                                 and r["counts"]["bonds"][0] == r["counts"]["bonds"][1]
                                 and all(abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6
                                         for a, b in r["box"].values()))
    r["emc_seed"] = (seed(p_dir), seed(c_dir))
    r["same_seed"] = r["emc_seed"][0] == r["emc_seed"][1] is not None
    r["emc_field"] = (field_named(p_dir), field_named(c_dir))
    ids = sorted(set(P["atoms"]) & set(C["atoms"]))
    dmax = max((max(abs(P["atoms"][a][k] - C["atoms"][a][k]) for k in (3, 4, 5)) for a in ids), default=None)
    same_mol = all(P["atoms"][a][0] == C["atoms"][a][0] for a in ids)
    r["coordinates"] = {"common_ids": len(ids), "max_abs_diff_A": dmax, "same_molecule_ids": same_mol,
                        "identical": dmax is not None and dmax < 1e-4 and len(ids) == len(P["atoms"]) == len(C["atoms"])}
    r["pairing"] = "strictly paired start (identical coordinates)" if r["coordinates"]["identical"] else "paired by seed only (coordinates differ)"
    # per-atom type-name mapping and charges
    pairs = collections.Counter()
    qsum = collections.defaultdict(lambda: [0.0, 0.0, 0])
    for a in ids:
        pn, cn = P["masses"].get(P["atoms"][a][1]), C["masses"].get(C["atoms"][a][1])
        pairs[(pn, cn)] += 1
        s = qsum[(pn, cn)]; s[0] += P["atoms"][a][2]; s[1] += C["atoms"][a][2]; s[2] += 1
    r["type_map_pcff_to_compass"] = {f"{k[0]}->{k[1]}": {"n": n,
                                     "mean_q_pcff": round(qsum[k][0] / qsum[k][2], 4),
                                     "mean_q_compass": round(qsum[k][1] / qsum[k][2], 4)}
                                     for k, n in sorted(pairs.items(), key=lambda kv: -kv[1])}
    r["masses_names"] = {"pcff": sorted(set(P["masses"].values())), "compass": sorted(set(C["masses"].values()))}
    r["net_charge"] = (round(sum(v[2] for v in P["atoms"].values()), 6), round(sum(v[2] for v in C["atoms"].values()), 6))
    # params file named field
    for tag, d in (("pcff", p_dir), ("compass", c_dir)):
        prm = d / "emc_build.params"
        txt = prm.read_text() if prm.exists() else ""
        r[f"params_{tag}"] = {"exists": prm.exists(),
                              "mentions_compass": "compass" in txt.lower(), "mentions_pcff": "pcff" in txt.lower(),
                              "head": [l for l in txt.splitlines()[:12] if l.strip()]}
    return r


if __name__ == "__main__":
    for arg in sys.argv[1:]:
        print(json.dumps(compare(int(arg)), indent=1, default=str))
