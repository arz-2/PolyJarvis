"""Unit tests for the equilibration drift gate (_analyse_property).

This is the function behind the PASS / EXTEND / ESCALATE verdict. A false PASS
would let an unequilibrated system flow into Tg and modulus extraction.
"""
import numpy as np

from check_equilibration_comprehensive import _analyse_property

# representative thresholds (mirror the script defaults)
DRIFT_PCT = 1.0
DRIFT_PVALUE = 0.05
BLOCKS = 5


def test_flat_series_is_equilibrated():
    rng = np.random.default_rng(0)
    values = 0.95 + rng.normal(0, 1e-4, size=200)
    res = _analyse_property(values, "density", DRIFT_PCT, DRIFT_PVALUE, BLOCKS)
    assert res["drift"]["pass"] is True
    assert res["block_sem"]["pass"] is True
    assert res["equilibrated"] is True


def test_strong_drift_is_not_equilibrated():
    values = np.linspace(0.90, 1.10, 200)  # steady, significant upward trend
    res = _analyse_property(values, "density", DRIFT_PCT, DRIFT_PVALUE, BLOCKS)
    assert res["drift"]["pass"] is False
    assert res["equilibrated"] is False
    assert res["drift"]["drift_pct"] > DRIFT_PCT


def test_result_structure():
    values = 0.95 + np.zeros(100)
    res = _analyse_property(values, "density", DRIFT_PCT, DRIFT_PVALUE, BLOCKS)
    for key in ("mean", "n_points", "drift", "block_sem", "equilibrated"):
        assert key in res
    assert res["n_points"] == 100


# ─── backbone path reconstruction ────────────────────────────────────────────
#
# The backbone is the graph diameter of the heavy-atom bond graph, NOT the
# atom-index order. Index order held only for a straight aliphatic chain; on the
# archive it gave PMMA1 160 "backbone" atoms against a true path of 81, with a
# median consecutive separation of 4.03 A.


class _FakeAtom:
    def __init__(self, index, mass, type_):
        self.index, self.mass, self.type = index, mass, type_


class _FakeBond:
    def __init__(self, a, b):
        self.atoms = (a, b)


class _FakeGroup:
    def __init__(self, atoms):
        self._atoms = list(atoms)
        self.positions = np.array([[a.index, 0.0, 0.0] for a in self._atoms], float)
        self.types = [a.type for a in self._atoms]


class _FakeAtomList(list):
    """A list that also accepts an index ARRAY, like an MDAnalysis AtomGroup."""

    def __getitem__(self, idx):
        if isinstance(idx, (list, np.ndarray)):
            return _FakeGroup([list.__getitem__(self, int(i)) for i in idx])
        return list.__getitem__(self, idx)


class _FakeChain:
    """Minimal stand-in for an MDAnalysis AtomGroup: atoms, bonds, types, universe."""

    def __init__(self, atoms, bonds):
        self.atoms = _FakeAtomList(atoms)
        self.bonds = bonds
        self.types = [a.type for a in atoms]
        self.universe = self


def _comb(n_backbone, n_branch_per_site, backbone_type=1, branch_type=9,
          branch_termini=False):
    """Linear backbone of n_backbone heavy atoms, each carrying pendant heavy atoms.

    Branch atoms get HIGHER indices than every backbone atom, so index order and bonded
    order disagree exactly the way a real side-group topology makes them.

    `branch_termini=False` leaves the two end sites bare, which is what a capped chain
    end looks like; True hangs a branch off them too (see the overshoot test).
    """
    atoms = [_FakeAtom(i, 12.0, backbone_type) for i in range(n_backbone)]
    bonds = [_FakeBond(atoms[i], atoms[i + 1]) for i in range(n_backbone - 1)]
    sites = range(n_backbone) if branch_termini else range(1, n_backbone - 1)
    nxt = n_backbone
    for site in sites:
        for _ in range(n_branch_per_site):
            b = _FakeAtom(nxt, 12.0, branch_type)
            atoms.append(b)
            bonds.append(_FakeBond(atoms[site], b))
            nxt += 1
    return _FakeChain(atoms, bonds)


def test_path_is_the_backbone_not_the_index_order():
    from check_equilibration_comprehensive import _backbone_atoms_sorted

    chain = _comb(n_backbone=20, n_branch_per_site=2)   # 20 backbone + 36 pendant
    _, idx = _backbone_atoms_sorted(chain, {1})
    # Every pendant carries an index above 19, so a walk that wandered into a side
    # group would show up here. The path is the backbone, in bonded order.
    assert sorted(idx) == list(range(20))
    assert list(idx) in (list(range(20)), list(range(19, -1, -1)))


def test_path_may_overshoot_by_one_atom_per_branched_terminus():
    """Documented, bounded behaviour: when a terminal site carries a branch, that
    branch atom is one bond further from the far end than the backbone terminus is, so
    the diameter ends on it. Costs at most one atom per end -- on the archive, PE1's
    242-atom path against a 240-atom typed backbone is exactly this."""
    from check_equilibration_comprehensive import _backbone_atoms_sorted

    chain = _comb(n_backbone=20, n_branch_per_site=1, branch_termini=True)
    _, idx = _backbone_atoms_sorted(chain, {1})
    assert len(idx) == 22
    # Strip the two path ENDS and the whole backbone is left, in order.
    assert sorted(int(i) for i in idx[1:-1]) == list(range(20))


def test_path_ignores_the_declared_types():
    """backbone_types validates the path; it does not select it. A selection that
    misses half the backbone (cis-PBD3 covered 49.8%) must not truncate the path."""
    from check_equilibration_comprehensive import _backbone_atoms_sorted

    chain = _comb(n_backbone=20, n_branch_per_site=1)
    _, idx_full = _backbone_atoms_sorted(chain, {1})
    for a in chain.atoms[:10]:
        a.type = 7                       # half the backbone now carries a foreign type
    chain.types = [a.type for a in chain.atoms]
    _, idx_partial = _backbone_atoms_sorted(chain, {1})
    assert len(idx_partial) == len(idx_full) == 20


def test_type_coverage_reports_a_misspecified_backbone():
    from check_equilibration_comprehensive import (_backbone_atoms_sorted,
                                                   backbone_type_coverage)

    chain = _comb(n_backbone=20, n_branch_per_site=1)
    for a in chain.atoms[:5]:
        a.type = 7
    chain.types = [a.type for a in chain.atoms]
    _, idx = _backbone_atoms_sorted(chain, {1})
    assert backbone_type_coverage(chain, idx, {1}) == 0.75


def test_hydrogens_cannot_extend_the_path():
    from check_equilibration_comprehensive import _backbone_atoms_sorted

    chain = _comb(n_backbone=10, n_branch_per_site=0)
    h1 = _FakeAtom(10, 1.008, 99)
    h2 = _FakeAtom(11, 1.008, 99)
    chain.atoms.extend([h1, h2])
    chain.bonds += [_FakeBond(chain.atoms[0], h1), _FakeBond(chain.atoms[9], h2)]
    chain.types = [a.type for a in chain.atoms]
    _, idx = _backbone_atoms_sorted(chain, {1})
    assert len(idx) == 10


def test_no_bond_topology_is_unavailable_not_guessed():
    from check_equilibration_comprehensive import _backbone_atoms_sorted

    chain = _comb(n_backbone=10, n_branch_per_site=0)
    chain.bonds = []
    _, idx = _backbone_atoms_sorted(chain, {1})
    assert idx is None


# ─── chain-dimension gate polarity ───────────────────────────────────────────
#
# The gate binds COLLAPSE only. Stiffness raises <Ree^2>/<Rg^2> (a rod gives 12),
# so CHAIN_EXTENDED is correct physics for the aromatic classes -- PSU1 measures
# 1.22x the finite-N ideal. Writing pass as (verdict == "CHAIN_GAUSSIAN") would
# silently make the gate two-sided and fail those cells for being what they are.


def _verdict_for(norm):
    """Replicate the classification for a given ratio/ideal, as the script does."""
    from check_equilibration_comprehensive import (CHAIN_RATIO_EXTENDED,
                                                   CHAIN_RATIO_MIN)
    if norm < CHAIN_RATIO_MIN:
        return "CHAIN_COLLAPSED"
    if norm > CHAIN_RATIO_EXTENDED:
        return "CHAIN_EXTENDED"
    return "CHAIN_GAUSSIAN"


def test_extended_chains_pass_the_gate():
    from orchestration.scripts.enforce_gate import chain_dimensions_gate

    for norm in (1.157, 1.220):                       # PEEK2, PSU1 as measured
        verdict = _verdict_for(norm)
        assert verdict == "CHAIN_EXTENDED"
        chain = {"dimensions": {"available": True, "verdict": verdict,
                                "pass": verdict != "CHAIN_COLLAPSED"}}
        assert chain_dimensions_gate(chain) is True, f"{norm} must not fail a Class A gate"


def test_collapsed_chains_fail_the_gate():
    from orchestration.scripts.enforce_gate import chain_dimensions_gate

    verdict = _verdict_for(0.634)                     # PMMA1 as measured
    assert verdict == "CHAIN_COLLAPSED"
    chain = {"dimensions": {"available": True, "verdict": verdict,
                            "pass": verdict != "CHAIN_COLLAPSED"}}
    assert chain_dimensions_gate(chain) is False


def test_archive_calibration_separates_only_pmma1():
    """0.72 is the midpoint of the one clean gap in the archive distribution. If a
    future edit moves it, this pins what it was calibrated to separate."""
    from check_equilibration_comprehensive import CHAIN_RATIO_MIN

    archive = {"PMMA1": 0.637, "PLA3": 0.806, "PVC1": 0.895, "PEEK3": 0.898,
               "PLA2": 0.901, "PMMA3": 0.911, "PLA1": 0.918, "cis-PBD2": 0.951,
               "PE2": 0.982, "PSU2": 1.000, "PEEK1": 1.018, "cis-PBD4": 1.047,
               "PLA4": 1.049, "cis-PBD3": 1.052, "cis-PBD1": 1.059, "PMMA2": 1.059,
               "PE1": 1.076, "PSU4": 1.086, "PE3": 1.140, "PEEK2": 1.157,
               "PSU1": 1.220}
    below = {k for k, v in archive.items() if v < CHAIN_RATIO_MIN}
    assert below == {"PMMA1"}


def test_unavailable_is_none_not_a_pass():
    from orchestration.scripts.enforce_gate import chain_dimensions_gate

    assert chain_dimensions_gate({"dimensions": {"available": False}}) is None
    assert chain_dimensions_gate({}) is None


def test_gate_is_binding_and_structural_in_both_regimes():
    from orchestration.scripts import enforce_gate as eg

    assert "chain_dimensions" in eg.BINDING_GLASSY
    assert "chain_dimensions" in eg.BINDING_RUBBERY
    # No trajectory length reshapes a glassy chain, so EXTEND is the wrong remedy.
    assert "chain_dimensions" in eg.STRUCTURAL_GATES
    assert "chain_dimensions" not in eg.EXTENDABLE_GATES
    assert "chain_dimensions" not in eg.ALWAYS_ADVISORY


def test_wrapped_coordinates_are_unmeasurable_not_collapsed():
    """The one path that could fail a good cell. If unwrap fails, R_ee is measured across
    a periodic boundary and comes out hugely foreshortened while all-atom Rg barely moves
    -- the ratio then reads as CHAIN_COLLAPSED and triggers a rebuild.

    Measured on archived PMMA1: backbone bond length 1.585 A unwrapped vs 9.86 A wrapped.
    That gap is what the window keys on, and every real backbone chemistry sits inside it
    (aromatic C-C 1.40, C-C 1.54, Si-O 1.64, C-S 1.82)."""
    from check_equilibration_comprehensive import (BACKBONE_BOND_A_MAX,
                                                   BACKBONE_BOND_A_MIN)

    for physical in (1.40, 1.54, 1.585, 1.64, 1.82):        # aromatic, C-C, PMMA, Si-O, C-S
        assert BACKBONE_BOND_A_MIN <= physical <= BACKBONE_BOND_A_MAX, physical
    for wrapped in (2.20, 3.37, 4.03, 9.86, 50.45):          # measured wrapped artifacts
        assert not (BACKBONE_BOND_A_MIN <= wrapped <= BACKBONE_BOND_A_MAX), wrapped


def test_unmeasurable_chain_dimensions_leave_the_gate_unarmed():
    from orchestration.scripts.enforce_gate import chain_dimensions_gate

    unmeasurable = {"dimensions": {"available": False,
                                   "reason": "backbone bond length 9.86 A is outside ..."}}
    assert chain_dimensions_gate(unmeasurable) is None, (
        "wrapped coordinates must not fail the gate — they make it unmeasurable")


def test_wrapped_coordinates_withdraw_the_finite_size_check():
    """The mirror-image failure to CHAIN_COLLAPSED, and the more dangerous direction.

    check_finite_size takes Rg from the TRAJECTORY, not from the .data file's image flags,
    so a failed unwrap shrinks Rg and INFLATES L/2Rg -- manufacturing a pass. Measured on
    archived PEEK1: Rg 24.62 A -> 18.13 A wrapped, carrying L/2Rg 0.900
    (SIZE_CHAIN_SELF_IMAGE) to 1.222 (SIZE_PASS)."""
    from check_equilibration_comprehensive import check_finite_size
    from orchestration.scripts.enforce_gate import finite_size_gate

    for kwargs in ({"coords_sane": False},
                   {"coords_sane": None, "unwrap_error": "AtomGroup has no fragments"}):
        fs = check_finite_size(data_file="/nonexistent.data", cutoff_A=9.5,
                               mean_rg_A=18.13, mean_ree_A=45.0, **kwargs)
        assert fs["available"] is False, kwargs
        assert "pass" not in fs, "an unmeasurable box check must not carry a verdict"
        assert finite_size_gate({"finite_size": fs}) is None, kwargs

    # Sane coordinates still evaluate: the guard withdraws, it does not disable.
    assert check_finite_size(data_file="/nonexistent.data", cutoff_A=9.5, mean_rg_A=24.62,
                             mean_ree_A=45.0, coords_sane=True)["reason"].startswith(
                                 "box unparseable")


def test_p2_without_a_backbone_is_unarmed_not_passing():
    """P2 is built from backbone bond vectors, so with no backbone every frame contributes
    0.0 and the mean is a perfect 0.0 -- which passed a BINDING Class A gate on no
    evidence."""
    from orchestration.scripts.enforce_gate import collect_gates

    gates = collect_gates({"thermo": {}, "chain": {},
                           "spatial": {"p2": {"available": False, "pass": None,
                                              "p2_mean": None}}})
    assert gates["p2"] is None
