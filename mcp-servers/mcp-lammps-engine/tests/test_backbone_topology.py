"""Unit tests for bond-topology backbone reconstruction (backbone_topology.py) and the
derive_backbone_types.py CLI built on it.

The core claim under test: the backbone is the graph diameter of the heavy-atom bond graph, not
a declared-type selection. A synthetic branched chain — a 5-atom straight backbone with a
1-atom pendant branch and a hydrogen — pins that the branch atom is excluded even though it
shares no distinguishing feature (mass, chemistry) with the true backbone atoms other than its
position off the main path.
"""
import subprocess
import sys
from pathlib import Path

import MDAnalysis as mda
import pytest

from backbone_topology import backbone_path, backbone_type_coverage

# 7 atoms, atom_style=full (id resid type charge x y z): a 5-atom straight backbone
# (ids 1-2-3-4-5, type 1), a pendant branch atom off atom 3 (id 6, type 2), and a
# hydrogen off atom 1 (id 7, type 3) that must not extend the walk.
BRANCHED_CHAIN_DATA = """\
# test polymer data file
7 atoms
6 bonds
3 atom types
1 bond types

0.0 20.0 xlo xhi
0.0 20.0 ylo yhi
0.0 20.0 zlo zhi

Masses

1 12.011 # c_bb
2 12.011 # c_branch
3 1.008 # h

Atoms

1 1 1 0.0 1.0 1.0 1.0
2 1 1 0.0 2.5 1.0 1.0
3 1 1 0.0 4.0 1.0 1.0
4 1 1 0.0 5.5 1.0 1.0
5 1 1 0.0 7.0 1.0 1.0
6 1 2 0.0 4.0 2.5 1.0
7 1 3 0.0 1.0 2.5 1.0

Bonds

1 1 1 2
2 1 2 3
3 1 3 4
4 1 4 5
5 1 3 6
6 1 1 7
"""


@pytest.fixture
def branched_data_file(tmp_path):
    p = tmp_path / "branched.data"
    p.write_text(BRANCHED_CHAIN_DATA)
    return p


# ── backbone_path ──────────────────────────────────────────────────────────

def test_backbone_path_excludes_pendant_branch(branched_data_file):
    u = mda.Universe(str(branched_data_file))
    chain = u.select_atoms("resid 1")
    _, idx = backbone_path(chain)
    assert idx is not None
    assert len(idx) == 5
    assert set(int(i) for i in u.atoms[idx].ids) == {1, 2, 3, 4, 5}


def test_backbone_path_excludes_hydrogen(branched_data_file):
    u = mda.Universe(str(branched_data_file))
    chain = u.select_atoms("resid 1")
    _, idx = backbone_path(chain)
    assert 6 not in set(int(i) for i in u.atoms[idx].ids)  # 0-based index of atom id 7


def test_backbone_path_none_below_two_heavy_atoms():
    u = mda.Universe.empty(1, trajectory=True)
    u.add_TopologyAttr("mass", [12.0])
    chain = u.select_atoms("all")
    pos, idx = backbone_path(chain)
    assert pos is None and idx is None


def test_backbone_type_coverage_full_when_types_match(branched_data_file):
    u = mda.Universe(str(branched_data_file))
    chain = u.select_atoms("resid 1")
    _, idx = backbone_path(chain)
    assert backbone_type_coverage(u, idx, {1}) == 1.0


def test_backbone_type_coverage_low_when_types_miss_the_path(branched_data_file):
    u = mda.Universe(str(branched_data_file))
    chain = u.select_atoms("resid 1")
    _, idx = backbone_path(chain)
    # declaring the BRANCH type as backbone_types should score poorly against the true path
    assert backbone_type_coverage(u, idx, {2}) == 0.0


def test_backbone_type_coverage_none_without_declared_types(branched_data_file):
    u = mda.Universe(str(branched_data_file))
    chain = u.select_atoms("resid 1")
    _, idx = backbone_path(chain)
    assert backbone_type_coverage(u, idx, set()) is None


# ── derive_backbone_types.py CLI ────────────────────────────────────────────

def test_derive_backbone_types_excludes_branch_type(branched_data_file):
    script = Path(__file__).resolve().parent.parent / "analysis_scripts" / "derive_backbone_types.py"
    out = subprocess.run(
        [sys.executable, str(script), "--data_file", str(branched_data_file)],
        capture_output=True, text=True, check=True,
    )
    import json
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["status"] == "success"
    assert result["backbone_types"] == [1]  # the branch's type 2 must not appear
    assert result["method"] == "heavy_atom_graph_diameter"
