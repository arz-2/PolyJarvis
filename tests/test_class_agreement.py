"""classify — does RadonPy's class label agree with THIS repo's own curation?

polymer_class is load-bearing far beyond naming: get_class_entry supplies charge_method,
electrostatics, cutoff_A, dt_fs, T_equil_K, density_initial_gcm3, the per-member
experimental bands and the tacticity default. A headless driver that picks the class
automatically is therefore choosing the whole protocol, so the label needs a standing
check against something this repo actually curated -- not against the classifier itself,
which would be circular.

Two references, deliberately kept apart:

  member_smiles   guides/polymer_rules.json's own hand-curated repeat units. THIS is the
                  binding reference -- it is the file the protocol is built from -- so
                  disagreements here are either overridden in guides/class_overrides.json
                  or they are bugs. Bar: 43/43 after overrides.

  PI1070          PoLyInfo's curated polymer_class column, via RadonPy's dataset. A
                  CHARACTERIZATION, not a bar: PoLyInfo answers "what is this polymer
                  called", this repo answers "which protocol does it get", and those
                  legitimately differ (PoLyInfo calls poly(aryl ether sulfone) POXI;
                  polymer_rules.json puts PSU under PSFO, and PSFO is what the protocol
                  wants). The count is pinned so a silent drop is visible.

Marked requires_binaries: shells into the mol-builder conda env for RadonPy.
"""
import csv
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))

from classify_cli import classify_batch  # noqa: E402

pytestmark = pytest.mark.requires_binaries

PI1070 = Path.home() / "RadonPy" / "data" / "PI1070.csv"

# Measured 2026-09-07 over all 1077 curated rows. Pinned as a floor, not an equality, so
# a RadonPy upgrade that IMPROVES agreement does not fail the suite -- only a regression does.
PI1070_AGREEMENT_FLOOR = 981


def _member_cases():
    rules = json.loads((REPO_ROOT / "guides" / "polymer_rules.json").read_text())["classes"]
    for cls, entry in rules.items():
        for name, smiles in (entry.get("member_smiles") or {}).items():
            # 'note' entries are prose explaining why a class has no curated molecule.
            if isinstance(smiles, list):
                for s in smiles:
                    yield cls, name, s


def test_every_curated_member_smiles_classifies_to_its_own_class():
    cases = list(_member_cases())
    assert cases, "polymer_rules.json exposes no member_smiles -- the reference is gone"

    results = classify_batch([s for _, _, s in cases])
    assert len(results) == len(cases)

    disagreements = [
        (name, cls, got.get("polymer_class"), got.get("polyinfo_class"), got.get("class_source"))
        for (cls, name, _s), got in zip(cases, results)
        if got.get("polymer_class") != cls
    ]
    assert not disagreements, (
        "classify disagrees with guides/polymer_rules.json member_smiles on:\n"
        + "\n".join(f"  {n}: rules say {c}, classify says {g} "
                    f"(polyinfo={p}, source={src})"
                    for n, c, g, p, src in disagreements)
        + "\n\nEither the override in guides/class_overrides.json is missing/wrong, or "
          "polymer_rules.json changed. Both are decisions for a human, not a test fix."
    )


def test_the_three_known_overrides_are_still_the_only_ones_needed():
    """The overrides file is a reviewed allowlist; it must not grow silently.

    If polyinfo starts agreeing on one of these, the override is dead weight and should be
    deleted -- that is a real signal, so this asserts each one is still LOAD-BEARING.
    """
    overrides = json.loads((REPO_ROOT / "guides" / "class_overrides.json").read_text())["overrides"]
    assert set(overrides) == {"*CC(*)Cl", "*CC(*)OC", "*Oc1cc(C)c(*)c(C)c1"}, (
        "guides/class_overrides.json changed. Every entry needs a member_smiles citation "
        "and a stated routing consequence -- see that file's _metadata.scope."
    )

    results = classify_batch(list(overrides))
    for smiles, got in zip(overrides, results):
        assert got["class_source"] == "override"
        assert got["polyinfo_class"] == overrides[smiles]["displaces"], (
            f"{smiles}: override claims it displaces {overrides[smiles]['displaces']}, "
            f"but polyinfo now says {got['polyinfo_class']}"
        )
        assert got["polymer_class"] == overrides[smiles]["polymer_class"]


@pytest.mark.skipif(not PI1070.is_file(), reason="RadonPy's PI1070.csv not present")
def test_agreement_with_polyinfo_curation_has_not_regressed():
    sys.path.insert(0, str(REPO_ROOT / "tools" / "ff_coverage"))
    from sweep import CLASS_BY_ID  # noqa: E402  (the id->code table the sweep itself used)

    cases = []
    with open(PI1070) as fh:
        for row in csv.DictReader(fh):
            try:
                code = CLASS_BY_ID.get(int(row["polymer_class"]))
            except (ValueError, TypeError, KeyError):
                continue
            if code:
                cases.append((code, row["smiles"]))

    results = classify_batch([s for _, s in cases], timeout=3000)
    agree = sum(1 for (curated, _), got in zip(cases, results)
                if got.get("polyinfo_class") == curated)
    assert agree >= PI1070_AGREEMENT_FLOOR, (
        f"agreement with PoLyInfo curation fell to {agree}/{len(cases)} "
        f"(floor {PI1070_AGREEMENT_FLOOR}). This is a characterization, not a correctness "
        "bar -- but a drop means the classifier or the seam changed behaviour."
    )
