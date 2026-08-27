"""backbone_rigidity.py — reference-polymer classification sanity check.

Real RDKit call (shells into the radonpy conda env, same pattern as
test_chem_similarity.py's real-RDKit smoke test) -- marked requires_binaries and run
explicitly (`pytest -m requires_binaries`), not part of the default suite.

The table below is the correctness bar this module was built around: PS's and PMMA's
pendant aromatic/ester groups must NOT make them look stiff (they sit off the backbone
path), while PEEK's and PSU's in-chain aromatic rings correctly should. PET anchors the
semi-rigid band between them.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "orchestration" / "scripts" / "backbone_rigidity.py"

REFERENCE_POLYMERS = [
    ("PE", "*CC*", "flexible"),
    ("PVC", "*CC(Cl)*", "flexible"),
    ("PVA", "*CC(O)*", "flexible"),
    ("PS", "*CC(*)c1ccccc1", "flexible"),
    ("PMMA", "*CC(*)(C)C(=O)OC", "flexible"),
    ("PLA", "*OC(=O)C(*)C", "flexible"),
    ("Nylon-6", "*CCCCCC(=O)N*", "flexible"),
    ("PET", "*OCCOC(=O)c1ccc(C(=O)*)cc1", "semi_rigid"),
    ("PEEK", "*Oc1ccc(C(=O)c2ccc(Oc3ccc(*)cc3)cc2)cc1", "stiff"),
    ("PSU", "*Oc1ccc(C(C)(C)c2ccc(Oc3ccc(S(=O)(=O)c4ccc(*)cc4)cc3)cc2)cc1", "stiff"),
    ("BPA-PC", "*Oc1ccc(C(C)(C)c2ccc(OC(*)=O)cc2)cc1", "stiff"),
]


def _run(smiles: str) -> dict:
    bash_script = (
        "source ~/miniforge3/etc/profile.d/conda.sh\n"
        "conda activate radonpy\n"
        f'python3 {SCRIPT} --smiles "$TEST_BACKBONE_RIGIDITY_SMILES" --output json\n'
    )
    import os
    env = dict(os.environ)
    env["TEST_BACKBONE_RIGIDITY_SMILES"] = smiles
    r = subprocess.run(["bash", "-c", bash_script], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=30, env=env)
    return json.loads(r.stdout.strip())


@pytest.mark.requires_binaries
@pytest.mark.parametrize("name,smiles,expected_class", REFERENCE_POLYMERS)
def test_reference_polymer_classification(name, smiles, expected_class):
    result = _run(smiles)
    assert "error" not in result, f"{name}: {result.get('error')}"
    assert result["rigidity_class"] == expected_class, (
        f"{name} ({smiles}): expected {expected_class}, got {result['rigidity_class']} "
        f"-- {result.get('classification_note')}"
    )


@pytest.mark.requires_binaries
def test_ps_pmma_pendant_groups_are_off_the_backbone_path():
    """The key correctness case: a pendant aromatic/ester group must not inflate
    backbone_ring_fraction, since it sits off the shortest path between the two `*`
    atoms."""
    for smiles in ("*CC(*)c1ccccc1", "*CC(*)(C)C(=O)OC"):
        result = _run(smiles)
        assert result["backbone_ring_fraction"] == 0.0
        assert result["backbone_rotatable_fraction"] == 1.0


@pytest.mark.requires_binaries
def test_malformed_smiles_is_an_error():
    result = _run("not a smiles")
    assert "error" in result


@pytest.mark.requires_binaries
def test_smiles_without_exactly_two_wildcards_is_an_error():
    result = _run("CC")  # no `*` atoms at all
    assert "error" in result
