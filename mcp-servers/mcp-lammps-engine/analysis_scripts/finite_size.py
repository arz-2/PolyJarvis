#!/usr/bin/env python3
"""Periodic self-imaging checks — the single implementation shared by the pre-submission
forecast (server.inspect_data_file) and the post-equilibration gate
(check_equilibration_comprehensive).

Two physical constraints on the box edge L = min(Lx, Ly, Lz):

  L >= 2*cutoff_A   Minimum-image convention for the pair potential. Below it an atom
                    interacts with its own periodic image and the POTENTIAL ITSELF is
                    wrong, so every downstream number is meaningless. (Also enforced
                    independently by script_generator.validate_data_file.)

  L >= 2*Rg         Each chain overlaps its own periodic images. The potential is fine,
                    but chain statistics, local packing and therefore density and the
                    elastic moduli are biased.

  L >= R_ee         A stricter statement of the same concern. ADVISORY only: running
                    slightly below R_ee is common in published polymer MD and is much
                    weaker evidence of a problem than the 2*Rg criterion.

WHY THE FORECAST EXISTS. Checking this only after equilibration wastes the entire chain:
a violating cell burns its full t_equil (3-20 ns by class) plus the cooling tail before
anything complains. Both inputs are knowable before a single MD step:

  * Rg barely changes between the packed cell and the equilibrated melt -- measured on
    the archive: PEEK1 24.67 -> 24.69 A, PSU2 27.19 -> 25.21, PMMA3 13.97 -> 14.29.
  * The box shrinks ~19% during npt_compress (EMC packs at density_initial ~0.5-0.6 and
    compresses to the real density), but the COMPRESSED edge is predictable from the
    cell's own mass and the target density to within -0.5%..-2.8% -- conservative, which
    is the correct direction for a gate.

Forecasting with that predicted edge catches all four archived violations (PEEK1, PSU4,
PSU2, PE2) with zero GPU time and no false positives on the runs that pass.
"""
import math
import re

import numpy as np

AVOGADRO = 6.02214076e23
CM3_PER_A3 = 1.0e-24


def parse_data_box_mass_rg(data_file):
    """Box edges (A), total mass (g/mol) and mass-weighted per-molecule mean Rg (A) from a
    LAMMPS .data file. Static -- no trajectory needed. Returns None if unparseable.

    Molecules are grouped by the .data molecule-ID column. Coordinates are UNWRAPPED with
    the per-atom image flags when the Atoms section carries them (x + ix*Lx, ...), which
    is what a write_data of an equilibrated cell emits. Without that, a chain straddling a
    periodic boundary is measured in its wrapped form and its Rg comes out far too small --
    on an equilibrated PEEK cell, 22.52 A against a true 28.41 A, enough to report
    L/2Rg = 1.037 PASS where the real value is 0.822 FAIL. A freshly packed cell has no
    image-flag columns (or all-zero ones), so the forecast path is unaffected.
    """
    L, masses, atoms = {}, {}, []
    section = None
    try:
        with open(data_file) as f:
            for line in f:
                s = line.strip()
                m = re.match(r"\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s+([xyz])lo\s+([xyz])hi", line)
                if m:
                    L[m.group(3)] = float(m.group(2)) - float(m.group(1))
                    continue
                head = s.split("#")[0].strip()
                if head in ("Masses", "Atoms", "Velocities", "Bonds", "Angles",
                            "Dihedrals", "Impropers", "Pair Coeffs", "Bond Coeffs"):
                    section = head
                    continue
                if not s:
                    continue
                t = s.split("#")[0].split()
                if section == "Masses" and len(t) >= 2:
                    try:
                        masses[int(t[0])] = float(t[1])
                    except ValueError:
                        pass
                elif section == "Atoms" and len(t) >= 7:
                    # full atom_style: id mol type q x y z [ix iy iz]
                    try:
                        img = ((int(t[7]), int(t[8]), int(t[9])) if len(t) >= 10
                               else (0, 0, 0))
                    except ValueError:
                        img = (0, 0, 0)
                    try:
                        atoms.append((int(t[1]), int(t[2]),
                                      float(t[4]), float(t[5]), float(t[6])) + img)
                    except ValueError:
                        pass
    except OSError:
        return None
    if len(L) != 3 or not atoms:
        return None

    box = (L["x"], L["y"], L["z"])
    images_present = any(a[5] or a[6] or a[7] for a in atoms)
    total_mass = sum(masses.get(a[1], 1.0) for a in atoms)
    mols = {}
    for mol_id, typ, x, y, z, ix, iy, iz in atoms:
        mols.setdefault(mol_id, []).append(
            (masses.get(typ, 1.0),
             x + ix * box[0], y + iy * box[1], z + iz * box[2]))
    rgs = []
    for members in mols.values():
        arr = np.asarray(members, dtype=float)
        w, pos = arr[:, 0], arr[:, 1:]
        wsum = w.sum()
        if wsum <= 0:
            continue
        com = (w[:, None] * pos).sum(axis=0) / wsum
        d = pos - com
        rgs.append(math.sqrt(float((w * (d ** 2).sum(axis=1)).sum() / wsum)))
    if not rgs:
        return None
    return {
        "box_A": [L["x"], L["y"], L["z"]],
        "L_min_A": float(min(L.values())),
        "total_mass_g_per_mol": float(total_mass),
        "mean_Rg_A": float(np.mean(rgs)),
        "n_molecules": len(mols),
        "image_flags_present": bool(images_present),
    }


def predict_equilibrated_L(total_mass_g_per_mol, target_density_gcm3):
    """Cubic box edge (A) the cell will occupy once compressed to target_density_gcm3.

    L = (m / (N_A * rho))^(1/3). Accurate to -0.5%..-2.8% against the archive's actual
    post-compression boxes, erring small -- i.e. slightly pessimistic, so the forecast
    does not wave through a cell that will in fact violate.
    """
    if not total_mass_g_per_mol or not target_density_gcm3 or target_density_gcm3 <= 0:
        return None
    volume_cm3 = total_mass_g_per_mol / (AVOGADRO * target_density_gcm3)
    return float((volume_cm3 / CM3_PER_A3) ** (1.0 / 3.0))


def classify_finite_size(L_A, cutoff_A, mean_rg_A, mean_ree_A=None):
    """Verdict + ratios for one (box, chain-size) pair.

    Returns SIZE_MIN_IMAGE_VIOLATION | SIZE_CHAIN_SELF_IMAGE | SIZE_PASS. `L >= R_ee` is
    reported via ree_self_image_flag but never decides the verdict.

    A missing cutoff_A leaves the minimum-image half UNEVALUATED, not passed. The 2*Rg
    half still binds (it is the criterion that discriminates -- realistic amorphous cells
    clear minimum image by 2-3x), so this is reported via min_image_evaluated rather than
    by withdrawing the whole gate, which would drop the 2*Rg check too.
    """
    if L_A is None or not mean_rg_A:
        return {"available": False, "reason": "need both a box edge and a mean Rg"}
    r_cut = (L_A / (2.0 * cutoff_A)) if cutoff_A else None
    r_rg = L_A / (2.0 * mean_rg_A)
    r_ree = (L_A / mean_ree_A) if mean_ree_A else None

    if r_cut is not None and r_cut < 1.0:
        verdict = "SIZE_MIN_IMAGE_VIOLATION"
    elif r_rg < 1.0:
        verdict = "SIZE_CHAIN_SELF_IMAGE"
    else:
        verdict = "SIZE_PASS"

    out = {
        "available": True,
        "pass": verdict == "SIZE_PASS",
        "verdict": verdict,
        "L_min_A": round(L_A, 2),
        "cutoff_A": cutoff_A,
        "L_over_2cutoff": round(r_cut, 3) if r_cut is not None else None,
        "L_over_2Rg": round(r_rg, 3),
        "L_over_Ree": round(r_ree, 3) if r_ree is not None else None,
        "ree_self_image_flag": bool(r_ree is not None and r_ree < 1.0),
        "min_image_evaluated": r_cut is not None,
    }
    if r_cut is None:
        out["min_image_unevaluated_reason"] = (
            "no cutoff_A supplied — L >= 2*cutoff_A was NOT checked; this verdict rests on "
            "the 2*Rg criterion alone. Pass cutoff_A (polymer_rules.json defines it for "
            "every class) to arm it."
        )
    return out


def nchain_scale_for(ratio, current_nchain=None):
    """How much to grow nchain to reach a ratio of 1.0.

    Cell volume is proportional to nchain at fixed density, so L grows as nchain^(1/3)
    and the required factor is (1/ratio)^3.
    """
    if not ratio or ratio <= 0 or ratio >= 1.0:
        return None
    factor = (1.0 / ratio) ** 3
    out = {"nchain_factor": round(factor, 2)}
    if current_nchain:
        out["nchain_suggested"] = int(math.ceil(current_nchain * factor))
    return out


def forecast_from_data_file(data_file, cutoff_A, target_density_gcm3, nchain=None):
    """Pre-submission forecast: will this built cell self-image once equilibrated?

    Grades the PREDICTED post-compression box against the packed cell's own Rg, and also
    reports the as-built box so an operator can see the compression the forecast assumes.
    """
    parsed = parse_data_box_mass_rg(data_file)
    if parsed is None:
        return {"available": False, "reason": f"could not parse box/coords from {data_file}"}

    L_pred = predict_equilibrated_L(parsed["total_mass_g_per_mol"], target_density_gcm3)
    if L_pred is None:
        # No target density to compress toward -- grade the as-built box instead, and say so.
        result = classify_finite_size(parsed["L_min_A"], cutoff_A, parsed["mean_Rg_A"])
        result["graded_box"] = "as_built"
        result["note"] = ("no target_density_gcm3 supplied, so the as-built box was graded; "
                          "it is ~20% larger than the compressed cell will be, making this "
                          "forecast optimistic")
        return result

    result = classify_finite_size(L_pred, cutoff_A, parsed["mean_Rg_A"])
    result.update({
        "graded_box": "predicted_equilibrated",
        "L_as_built_A": round(parsed["L_min_A"], 2),
        "L_predicted_A": round(L_pred, 2),
        "target_density_gcm3": target_density_gcm3,
        "packed_Rg_A": round(parsed["mean_Rg_A"], 2),
        "n_molecules": parsed["n_molecules"],
    })
    if not result["pass"]:
        ratio = (result["L_over_2cutoff"] if result["verdict"] == "SIZE_MIN_IMAGE_VIOLATION"
                 else result["L_over_2Rg"])
        remedy = nchain_scale_for(ratio, nchain)
        if remedy:
            result["remedy"] = remedy
    return result
