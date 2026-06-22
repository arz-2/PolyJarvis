"""Scripted-baseline driver wiring: deterministic plan -> foundation dispatch -> metrics."""
import scripted_baseline
from scripted_baseline import run_scripted_baseline


def test_dry_smoke_iterates_foundation(tmp_path):
    m = run_scripted_baseline(
        run_name="SMOKE", polymer_class="PHYC", smiles="*CC*",
        properties={"density"}, work_dir=str(tmp_path), seed=1001,
        gpu_ids="0", mpi=8, execute=False, smoke=True)
    # build -> equil -> equil-check all dispatched (dry), then halts at the first
    # non-foundation stage (run-summary), which is out of scope this pass.
    assert m.stages_completed == ["build", "equil", "equil-check"]
    assert m.terminal_state == "completed_foundation"
    assert m.arm == "script"
    d = m.to_dict()
    assert d["seed"] == 1001 and "_t0" not in d


def test_halt_on_failure_classifies_and_does_not_recover(monkeypatch, tmp_path):
    # The SCRIPT arm's reason to exist: detect a failure, classify it, halt with NO
    # recovery. Force equil-check to fail with a real LAMMPS error string.
    def boom(ctx, execute, smoke):
        return False, "ERROR: Out of range atoms - cannot compute PPPM", "forced fail"
    monkeypatch.setitem(scripted_baseline.DISPATCH, "equil-check", boom)

    m = run_scripted_baseline(
        run_name="HALT", polymer_class="PHYC", smiles="*CC*",
        properties={"density"}, work_dir=str(tmp_path), seed=1,
        gpu_ids="0", mpi=8, execute=False, smoke=True)

    assert m.terminal_state == "stalled"
    assert m.stages_completed == ["build", "equil"]   # halted at equil-check
    assert len(m.recovery_events) == 1
    ev = m.recovery_events[0]
    assert ev.fault == "pppm_out_of_range"
    assert ev.prescripted is True       # it IS a recover.md row...
    assert ev.resolved is False         # ...but SCRIPT performs no recovery
