"""Force-field capability: the hard gate, and the two bugs that made it lie.

Both bugs this file locks against reported the OPPOSITE of the truth rather than
failing loudly: a style parser that dropped every section reported nothing
available, and an EMC probe that never ran EMC reported everything available.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

import forcefield as fc  # noqa: E402

# `lmp -h` puts a blank line directly under each header and ends a section only at
# the next header. Reproduced verbatim -- this exact shape broke the first parser.
LMP_H = """\
Large-scale Atomic/Molecular Massively Parallel Simulator - 22 Jul 2025

* Pair styles:

lj/class2       lj/class2/kk    lj/class2/coul/long
lj/class2/coul/long/kk          lj/cut/coul/long
lj/cut/coul/long/kk

* Bond styles:

class2          class2/kk       harmonic        harmonic/kk

* Angle styles:

class2          class2/kk       harmonic        harmonic/kk

* Dihedral styles:

class2          class2/kk       opls            opls/kk         fourier

* Improper styles:

class2          class2/kk       cvff            umbrella

* Fix styles

nve             npt
"""


@pytest.fixture
def styles(monkeypatch):
    monkeypatch.setattr(fc.subprocess, "run", lambda *a, **k: type("R", (), {
        "returncode": 0, "stdout": LMP_H})())
    return fc.installed_styles("/fake/lmp")


# ─── style parsing ─────────────────────────────────────────────────────────────

def test_blank_line_under_header_does_not_end_the_section(styles):
    """The original bug: a blank line reset the parser, so every section came back
    empty and every field was reported as missing all its styles."""
    assert "lj/class2" in styles["pair"]
    assert styles["bond"] == {"class2", "class2/kk", "harmonic", "harmonic/kk"}


def test_only_the_five_interaction_sections_are_captured(styles):
    """`Fix styles` has no colon and must not be picked up as an interaction kind."""
    assert set(styles) == {"pair", "bond", "angle", "dihedral", "improper"}
    assert "nve" not in styles.get("improper", set())


def test_unreadable_binary_yields_no_styles(monkeypatch):
    def boom(*a, **k):
        raise OSError("no such binary")
    monkeypatch.setattr(fc.subprocess, "run", boom)
    assert fc.installed_styles("/nonexistent/lmp") == {}


def test_failed_lmp_invocation_is_not_read_as_partial_output(monkeypatch):
    """A nonzero exit with truncated stdout would silently report real styles as
    missing -- the same class of failure as the blank-line bug."""
    monkeypatch.setattr(fc.subprocess, "run", lambda *a, **k: type("R", (), {
        "returncode": 1, "stdout": "* Pair styles:\n\nlj/class2\n"})())
    assert fc.installed_styles("/fake/lmp") == {}


# ─── integration ───────────────────────────────────────────────────────────────

def test_class2_field_integrates_and_is_fully_kokkos(styles):
    r = fc.check_integration("pcff", styles)
    assert r["integrates"] and r["missing_styles"] == []
    assert r["gpu_accelerated"] is True
    assert r["styles_without_kokkos"] == []


def test_kokkos_gap_names_the_offending_style(styles):
    """OPLS is fully runnable but improper cvff has no /kk, so it runs host-side.
    A bare boolean hides which term costs the transfer."""
    r = fc.check_integration("opls/2024/opls-aa", styles)
    assert r["integrates"] is True
    assert r["gpu_accelerated"] is False
    assert r["styles_without_kokkos"] == ["improper_style cvff"]


def test_missing_style_is_reported_with_its_kind(monkeypatch):
    partial = {"pair": set(), "bond": {"class2"}, "angle": {"class2"},
               "dihedral": {"class2"}, "improper": {"class2"}}
    r = fc.check_integration("pcff", partial)
    assert r["integrates"] is False
    assert "pair_style lj/class2/coul/long" in r["missing_styles"]
    assert r["gpu_accelerated"] is None


# ─── typing probe ──────────────────────────────────────────────────────────────

def test_emc_probe_actually_runs_emc(monkeypatch, tmp_path):
    """`--esh-only` writes the input script and stops without running EMC, so a
    probe carrying that flag reports every EMC field as typeable. It must not."""
    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr(fc.subprocess, "run", fake_run)
    fc._try_emc("*CC*", "pcff", str(tmp_path))
    assert "--esh-only" not in seen["cmd"]
    assert "--field" in seen["cmd"] and "pcff" in seen["cmd"]


def test_emc_failure_surfaces_the_engine_message(monkeypatch, tmp_path):
    monkeypatch.setattr(fc.subprocess, "run", lambda cmd, **kw: type("R", (), {
        "returncode": 1, "stdout": "",
        "stderr": "ScriptFieldEntryApply: Missing force field parameters"})())
    ok, err = fc._try_emc("*CC*", "compass", str(tmp_path))
    assert ok is False
    assert "Missing force field parameters" in err


def test_typing_is_skipped_when_the_field_cannot_run(monkeypatch):
    """Building a cell for a field LAMMPS cannot integrate is wasted minutes."""
    monkeypatch.setattr(fc, "installed_styles", lambda lmp: {
        "pair": set(), "bond": set(), "angle": set(),
        "dihedral": set(), "improper": set()})
    called = []
    monkeypatch.setattr(fc, "check_typing",
                        lambda s, f: called.append(f) or {"types_smiles": True})
    out = fc.assess_all("*CC*", ["pcff"])
    assert called == []
    assert out["fields"]["pcff"]["candidate"] is False
    assert out["fields"]["pcff"]["types_smiles"] is None


def test_emc_success_is_recorded_as_a_built_cell(monkeypatch):
    monkeypatch.setattr(fc, "_try_emc", lambda s, n, w: (True, ""))
    r = fc.check_typing("*CC*", "pcff")
    assert r["typing_evidence"] == "built_cell"
    assert r["further_steps_required"] == []


def test_radonpy_success_is_typing_only_and_names_the_missing_step(monkeypatch):
    """ff_assign proves atom types and bonded parameters -- NOT a runnable cell.
    GAFF2 still needs its per-chemistry QM charge step, and the whole
    'GAFF2 is PEEK's only alternative' claim rests on this distinction."""
    monkeypatch.setattr(fc, "_try_radonpy", lambda s, f: (True, ""))
    r = fc.check_typing("*CC*", "gaff2")
    assert r["typing_evidence"] == "typed_only"
    assert any("QM charge" in s for s in r["further_steps_required"])


def test_candidate_lists_are_split_by_evidence_standard(monkeypatch):
    monkeypatch.setattr(fc, "installed_styles", lambda lmp: {
        k: {"lj/class2/coul/long", "class2", "lj/cut/coul/long", "harmonic",
            "fourier", "cvff"} for k in ("pair", "bond", "angle", "dihedral", "improper")})
    monkeypatch.setattr(fc, "_try_emc", lambda s, n, w: (True, ""))
    monkeypatch.setattr(fc, "_try_radonpy", lambda s, f: (True, ""))
    out = fc.assess_all("*CC*", ["pcff", "gaff2"])
    assert out["candidates_built_cell"] == ["pcff"]
    assert out["candidates_typed_only"] == ["gaff2"]


# ─── the anti-gate guard ───────────────────────────────────────────────────────

def test_candidate_is_never_sold_as_an_accuracy_claim(monkeypatch):
    """Buildability is the one hard gate in field selection. It is also the one most
    likely to be mistaken for a recommendation -- DREIDING types every family here
    and is the least trustworthy of them for condensed-phase density."""
    monkeypatch.setattr(fc, "installed_styles", lambda lmp: {
        k: {"lj/class2/coul/long", "class2"}
        for k in ("pair", "bond", "angle", "dihedral", "improper")})
    monkeypatch.setattr(fc, "_try_emc", lambda s, n, w: (True, ""))
    out = fc.assess_all("*CC*", ["pcff"])
    assert "NOT a claim about accuracy" in out["note"]
    assert out["candidates"] == ["pcff"]


def test_excluded_fields_carry_a_reason(monkeypatch):
    """polystyrene is the load-bearing one: PS is a deficit family, so the next
    reader will reach for it. It is a coarse-grained tabulated potential."""
    assert "coarse-grained" in fc.EXCLUDED["polystyrene"]
    assert set(fc.EXCLUDED) & {"cff", "uff", "martini"}
    assert all(v.strip() for v in fc.EXCLUDED.values())
    assert not (set(fc.EXCLUDED) & set(fc.FIELDS))


def test_opls_ua_is_registered_with_no_improper_style():
    """~/emc/field/opls/{2012,2024}/opls-ua.prm has no final ITEM IMPROPER params
    list (2012 has only IMPROPER_AUTO derivation rules; 2024 has none at all) --
    unlike opls-aa, so requiring an improper style here would wrongly reject an
    admissible field on integration alone."""
    for name in ("opls/2024/opls-ua", "opls/2012/opls-ua"):
        assert name in fc.FIELDS, f"{name} missing from FIELDS registry"
        assert "improper" not in fc.FIELDS[name]["styles"]
        assert fc.FIELDS[name]["front_end"] == "emc"
