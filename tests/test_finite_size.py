"""Periodic self-imaging checks — the shared module behind both the pre-submission forecast
(server.inspect_data_file) and the post-equilibration gate (check_equilibration_comprehensive).

The point of the forecast is cost: a cell whose chains overlap their own periodic images is
knowable before any MD, and catching it at the equilibration gate instead burns the whole
chain (3-20 ns of t_equil by class, plus the cooling tail). These tests lock in that the
forecast actually fires on the archive's four violating cells and stays quiet on the rest.
"""
import math
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "mcp-servers" / "mcp-lammps-engine" / "analysis_scripts"))

from finite_size import (  # noqa: E402
    classify_finite_size,
    forecast_from_data_file,
    nchain_scale_for,
    parse_data_box_mass_rg,
    predict_equilibrated_L,
)

ARCHIVE = REPO_ROOT / "manuscript" / "data"

# family -> (experimental density g/cm3, cutoff_A, nchain)
FAM = {
    "PEEK": (1.300, 12.0, 8), "PSU": (1.240, 12.0, 8), "PE": (0.930, 14.0, 20),
    "PMMA": (1.180, 12.0, 10), "PLA": (1.250, 12.0, 10), "cis-PBD": (0.910, 12.0, 20),
}


def _cell(run):
    return ARCHIVE / run / "lammps" / "cell" / "cell.data"


def _has(run):
    return _cell(run).exists()


# ─── classify: verdict precedence and polarity ─────────────────────────────────

def test_min_image_outranks_chain_self_image():
    """A cell violating both must report the minimum-image verdict: that one means the pair
    potential is wrong, which is strictly worse than biased chain statistics."""
    r = classify_finite_size(L_A=20.0, cutoff_A=12.0, mean_rg_A=15.0)
    assert r["verdict"] == "SIZE_MIN_IMAGE_VIOLATION"
    assert r["pass"] is False


def test_moderate_self_imaging_is_advisory_not_a_rebuild():
    """PEEK1's real archived geometry: L/2Rg = 0.737, minimum image fine at 1.515.

    GRADED 2026-09-02. This used to be a hard SIZE_CHAIN_SELF_IMAGE, routing STRUCTURAL_FAIL and
    a rebuild. `L >= 2*Rg` has no hard standing in the literature -- the founding atomistic paper
    (Theodorou & Suter 1985) ran at 0.53, and 17.2% of RadonPy's validated 1,077-polymer dataset
    sits below 1.0. Measured cost at this severity (Anstine 2020, atoms held fixed, 1 chain vs
    33): density <= 0.6%, modulus inside the force-field spread. Reported, never blocking."""
    r = classify_finite_size(L_A=36.37, cutoff_A=12.0, mean_rg_A=24.69, mean_ree_A=55.89)
    assert r["verdict"] == "SIZE_CHAIN_SELF_IMAGE_ADVISORY"
    assert r["pass"] is True and r["self_image_advisory"] is True
    assert r["L_over_2cutoff"] == 1.515
    assert r["L_over_2Rg"] == 0.737


def test_severe_self_imaging_still_binds():
    """Below SELF_IMAGE_BINDING_RATIO the cell is rebuilt. The boundary is a judgement call
    (see the constant's own note) -- pinned here so moving it is a deliberate act."""
    import finite_size as fs
    r = classify_finite_size(L_A=0.45 * 2 * 24.69, cutoff_A=5.0, mean_rg_A=24.69)
    assert r["verdict"] == "SIZE_CHAIN_SELF_IMAGE"
    assert r["pass"] is False
    assert fs.SELF_IMAGE_BINDING_RATIO == 0.5


def test_minimum_image_still_binds_at_any_ratio():
    """The one criterion with unambiguous standing: below it an atom interacts with its own
    image and the pair potential itself is wrong. Never graded."""
    r = classify_finite_size(L_A=20.0, cutoff_A=12.0, mean_rg_A=5.0)
    assert r["verdict"] == "SIZE_MIN_IMAGE_VIOLATION"
    assert r["pass"] is False
    assert r["L_over_2Rg"] >= 1.0          # the Rg half is fine; minimum image is not


def test_ree_below_one_alone_still_passes():
    """L < R_ee is advisory: common in published polymer MD, and much weaker evidence than
    the 2*Rg criterion. It must be reported without deciding the verdict."""
    r = classify_finite_size(L_A=50.9, cutoff_A=14.0, mean_rg_A=24.33, mean_ree_A=59.81)
    assert r["verdict"] == "SIZE_PASS"
    assert r["pass"] is True
    assert r["ree_self_image_flag"] is True


def test_missing_inputs_are_unavailable_not_failures():
    assert classify_finite_size(None, 12.0, 15.0)["available"] is False
    assert classify_finite_size(40.0, 12.0, None)["available"] is False


def test_cutoff_omitted_leaves_min_image_unevaluated_not_passed():
    """The 2*Rg half must keep binding -- withdrawing the whole gate would drop the
    criterion that actually discriminates -- but the omission must be explicit, not silent."""
    r = classify_finite_size(L_A=40.0, cutoff_A=None, mean_rg_A=15.0)
    assert r["verdict"] == "SIZE_PASS"
    assert r["L_over_2cutoff"] is None
    assert r["L_over_2Rg"] == round(40.0 / 30.0, 3)
    assert r["min_image_evaluated"] is False
    assert "cutoff_A" in r["min_image_unevaluated_reason"]


def test_cutoff_supplied_marks_min_image_evaluated():
    r = classify_finite_size(L_A=40.0, cutoff_A=12.0, mean_rg_A=15.0)
    assert r["min_image_evaluated"] is True
    assert "min_image_unevaluated_reason" not in r


# ─── predicted box edge ────────────────────────────────────────────────────────

def test_predict_equilibrated_L_matches_closed_form():
    # 1 mol of a 100 g/mol species at 1 g/cm3 occupies 100 cm3
    L = predict_equilibrated_L(100.0, 1.0)
    expected = ((100.0 / 6.02214076e23) / 1.0e-24) ** (1 / 3)
    assert math.isclose(L, expected, rel_tol=1e-9)


def test_predict_equilibrated_L_guards_bad_input():
    assert predict_equilibrated_L(0, 1.0) is None
    assert predict_equilibrated_L(1000.0, 0) is None
    assert predict_equilibrated_L(1000.0, None) is None


def test_denser_target_gives_smaller_box():
    assert predict_equilibrated_L(1e5, 1.4) < predict_equilibrated_L(1e5, 0.9)


# ─── nchain remedy ─────────────────────────────────────────────────────────────

def test_nchain_scale_is_inverse_cube():
    """L grows as nchain^(1/3) at fixed density, so closing a ratio needs (1/ratio)^3."""
    out = nchain_scale_for(0.5, current_nchain=8)
    assert out["nchain_factor"] == 8.0
    assert out["nchain_suggested"] == 64


def test_nchain_scale_none_when_already_passing():
    assert nchain_scale_for(1.0) is None
    assert nchain_scale_for(1.4) is None


# ─── forecast against the real archive ─────────────────────────────────────────

@pytest.mark.skipif(not _has("PEEK1"), reason="archived build cells not present")
@pytest.mark.parametrize("run", ["PEEK1", "PSU4", "PSU2", "PE2"])
def test_forecast_catches_the_four_archived_violations(run):
    """These four are exactly the cells the post-equilibration gate flags. Catching them
    here means no GPU time is spent on them at all."""
    rho, cutoff, nchain = FAM[run.rstrip("0123456789")]
    f = forecast_from_data_file(str(_cell(run)), cutoff, rho, nchain=nchain)
    assert f["available"] is True
    assert f["verdict"] == "SIZE_CHAIN_SELF_IMAGE", f
    assert f["graded_box"] == "predicted_equilibrated"
    assert f["remedy"]["nchain_suggested"] > nchain


@pytest.mark.skipif(not _has("PMMA3"), reason="archived build cells not present")
@pytest.mark.parametrize("run", ["PMMA3", "PLA2", "cis-PBD1"])
def test_forecast_no_false_positives(run):
    rho, cutoff, nchain = FAM[run.rstrip("0123456789")]
    f = forecast_from_data_file(str(_cell(run)), cutoff, rho, nchain=nchain)
    assert f["verdict"] == "SIZE_PASS", f
    assert "remedy" not in f


@pytest.mark.skipif(not _has("PEEK1"), reason="archived build cells not present")
def test_forecast_grades_the_compressed_box_not_the_packed_one():
    """The as-built cell is ~20% roomier than the compressed one, so grading the as-built box
    would wave PSU2 and PE2 through. PEEK1 passes on neither, but must still be graded on the
    predicted edge, and that edge must be the smaller of the two."""
    rho, cutoff, nchain = FAM["PEEK"]
    f = forecast_from_data_file(str(_cell("PEEK1")), cutoff, rho, nchain=nchain)
    assert f["L_predicted_A"] < f["L_as_built_A"]


@pytest.mark.skipif(not _has("PSU2"), reason="archived build cells not present")
def test_as_built_box_would_miss_a_real_violation():
    """Documents why the prediction step exists: PSU2's as-built box passes the 2*Rg test and
    its compressed box does not."""
    parsed = parse_data_box_mass_rg(str(_cell("PSU2")))
    as_built = classify_finite_size(parsed["L_min_A"], 12.0, parsed["mean_Rg_A"])
    assert as_built["verdict"] == "SIZE_PASS"
    forecast = forecast_from_data_file(str(_cell("PSU2")), 12.0, FAM["PSU"][0])
    assert forecast["verdict"] == "SIZE_CHAIN_SELF_IMAGE"


@pytest.mark.skipif(not _has("PEEK1"), reason="archived build cells not present")
def test_no_target_density_grades_as_built_and_says_so():
    """Without a target density the forecast must not silently pretend to be predictive."""
    f = forecast_from_data_file(str(_cell("PEEK1")), 12.0, None)
    assert f["graded_box"] == "as_built"
    assert "optimistic" in f["note"]


def test_unparseable_file_is_unavailable():
    f = forecast_from_data_file("/nonexistent/cell.data", 12.0, 1.2)
    assert f["available"] is False


# ─── the SIZE_ prefix contract ─────────────────────────────────────────────────

def test_all_failure_verdicts_share_the_size_prefix():
    """server.inspect_data_file prefixes its blocking error with the verdict, and
    run_campaign.do_build filters validation.errors on 'SIZE_'. Both depend on
    every failing verdict starting with that token."""
    fails = [
        classify_finite_size(20.0, 12.0, 15.0)["verdict"],       # min image
        classify_finite_size(36.4, 12.0, 24.7)["verdict"],       # chain self image
    ]
    assert all(v.startswith("SIZE_") for v in fails)
    assert classify_finite_size(60.0, 12.0, 15.0)["verdict"] == "SIZE_PASS"


# ─── image flags: a wrapped chain must not read as small ───────────────────────

def _write_data(tmp_path, atom_lines, box=50.0):
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "cell.data"
    p.write_text(
        "LAMMPS data\n\n"
        f"{len(atom_lines)} atoms\n1 atom types\n\n"
        f"0.0 {box} xlo xhi\n0.0 {box} ylo yhi\n0.0 {box} zlo zhi\n\n"
        "Masses\n\n1 12.0\n\nAtoms\n\n" + "\n".join(atom_lines) + "\n")
    return p


def test_image_flags_unwrap_a_chain_split_across_the_boundary(tmp_path):
    """One molecule whose two halves sit at opposite faces of the box. Read wrapped it looks
    tiny; with image flags it is one extended chain. This is the PEEK1 failure: wrapped Rg
    22.52 vs true 28.41 turned a real 0.822 FAIL into a reported 1.037 PASS."""
    wrapped = _write_data(tmp_path, [
        "1 1 1 0.0  1.0 25.0 25.0 0 0 0",
        "2 1 1 0.0  2.0 25.0 25.0 0 0 0",
        "3 1 1 0.0 48.0 25.0 25.0 -1 0 0",
        "4 1 1 0.0 49.0 25.0 25.0 -1 0 0",
    ])
    r = parse_data_box_mass_rg(str(wrapped))
    assert r["image_flags_present"] is True
    # unwrapped the chain spans 1.0 -> -1.0 (49-50), i.e. a compact ~1 A object,
    # whereas reading it wrapped would report a ~24 A half-box spread
    assert r["mean_Rg_A"] < 5.0


def test_zero_image_flags_leave_coordinates_untouched(tmp_path):
    """A freshly packed cell has no image flags, so the forecast path is unchanged."""
    lines_no_flags = ["1 1 1 0.0 10.0 25.0 25.0", "2 1 1 0.0 30.0 25.0 25.0"]
    lines_zero_flags = [ln + " 0 0 0" for ln in lines_no_flags]
    a = parse_data_box_mass_rg(str(_write_data(tmp_path / "a", lines_no_flags)))
    b = parse_data_box_mass_rg(str(_write_data(tmp_path / "b", lines_zero_flags)))
    assert a["mean_Rg_A"] == pytest.approx(b["mean_Rg_A"])
    assert a["image_flags_present"] is False


def test_trailing_comment_on_an_atom_line_is_ignored(tmp_path):
    p = _write_data(tmp_path, ["1 1 1 0.0 10.0 25.0 25.0 0 0 0  # chain A",
                               "2 1 1 0.0 30.0 25.0 25.0 0 0 0"])
    assert parse_data_box_mass_rg(str(p))["n_molecules"] == 1
