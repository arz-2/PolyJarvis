"""Fault injection fires; classifier labels correctly; prescripted recoveries resolve."""
import pytest

from fault_catalog import CATALOG
from run_recovery_benchmark import run_one


@pytest.mark.parametrize("fault", CATALOG, ids=[f.id for f in CATALOG])
def test_fault_injects_and_is_labeled(fault, tmp_path):
    row = run_one(fault, tmp_path)
    assert row["triggered"], f"{fault.id} did not fire"
    assert row["classifier_ok"], f"{fault.id} mislabeled: {row}"


def test_prescripted_recoveries_resolve(tmp_path):
    for fault in CATALOG:
        if not fault.prescripted:
            continue
        row = run_one(fault, tmp_path)
        assert row["recovery_resolved"], f"{fault.id} prescripted recovery failed"


def test_inferred_left_for_agent(tmp_path):
    inferred = [f for f in CATALOG if not f.prescripted]
    assert len(inferred) == 2  # F5, F6 — generalization probes
    for fault in inferred:
        row = run_one(fault, tmp_path)
        assert row["recovery_resolved"] is False
