"""The failure-injection benchmark must keep injecting failures.

benchmarks/recovery_r2/injectors.py claims each perturbation of a real EMC cell produces a
specific Finding code. The claim is only worth something if it is checked: a validation-path
change could silently stop an injector firing, and the benchmark would then report a ladder
that was never actually driven.

Marked requires_binaries because classify() imports the LAMMPS engine server module and reads
a real built cell -- there is nothing to inject into on a checkout with no completed build.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "benchmarks" / "recovery_r2"))

import injectors  # noqa: E402


@pytest.fixture(scope="module")
def cell():
    data, params = injectors.find_cell()
    if not data:
        pytest.skip("no completed build with a cell + params under data/")
    return data, params


def test_every_injector_targets_a_code_the_registry_routes():
    """Pure logic, no cell needed: an injector aimed at an unrouted or unreachable code
    would fire nothing and silently measure nothing."""
    sys.path.insert(0, str(REPO_ROOT / "benchmarks" / "recovery_r2"))
    from code_inventory import inventory

    inv = inventory()
    live = {**inv["live_automatic"], **inv["live_agent_only"]}
    for inj in injectors.INJECTORS:
        assert inj.target_code not in inv["unreachable"], (
            f"{inj.id} targets {inj.target_code}, which no producer mints")
        assert inj.target_code in live, (
            f"{inj.id} targets {inj.target_code}, which default_remedies() does not route")


@pytest.mark.requires_binaries
def test_clean_cell_is_a_valid_control(cell):
    """Without this the whole benchmark is void: an injector that 'fires' on a cell already
    failing validation is measuring the cell, not the injection."""
    data, params = cell
    code, errors = injectors.classify(data, params)
    assert code is None, f"clean cell already fails with {code}: {errors}"


@pytest.mark.requires_binaries
def test_every_injector_fires_its_target_code(cell):
    data, params = cell
    result = injectors.verify(data, params)
    assert not result["failures"], result["failures"]
    assert all(row["fired"] for row in result["injectors"])


@pytest.mark.requires_binaries
def test_injection_does_not_touch_the_source_cell(cell):
    """Injection works on copies. A benchmark that corrupts a campaign's own build would
    destroy the run it borrowed the cell from."""
    data, params = cell
    before = data.read_bytes()
    injectors.verify(data, params)
    assert data.read_bytes() == before


def test_every_llm_only_claim_names_a_key_in_the_override_contract():
    """The Class-3 claim -- 'only a reasoning agent can resolve this' -- is falsifiable.

    If the named fix is not in ALLOWED_OVERRIDES then no agent could apply it either, and the
    fault belongs in Class 2 (unresolvable). A benchmark whose headline metric is 'Class-3
    trials the LLM arm resolved' is only as honest as this check.
    """
    sys.path.insert(0, str(REPO_ROOT / "benchmarks" / "recovery_r2"))
    import resolvability

    table = resolvability.classify_codes()
    assert not resolvability.validate(table)
    llm_only = [c for c, e in table.items() if e["class"].startswith("3_")]
    assert llm_only, "no Class-3 faults left -- the ablation would measure the LLM at zero by construction"


def test_the_three_classes_are_all_populated():
    """A partition with an empty Class 1 or Class 2 is a rigged denominator: Class 1 shows
    what the deterministic core already handles, Class 2 shows what nothing can fix. Reporting
    Class 3 without both makes the LLM's contribution unauditable."""
    sys.path.insert(0, str(REPO_ROOT / "benchmarks" / "recovery_r2"))
    import resolvability

    classes = {e["class"].split("_")[0] for e in resolvability.classify_codes().values()}
    assert {"1", "2", "3"} <= classes, f"missing a class: {sorted(classes)}"
