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
