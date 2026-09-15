"""Create workflow_state for PEG_COMPASS_1..3 only, pin remedy counters, record the lock.

WorkflowEngine is constructed ONLY on the new run directories (executor=None), so
_load_or_create_state writes a fresh state whose plan_hash matches the final plan.
PEG_1..3 workflow_state.json are hashed before and after to prove they were not touched.
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path("/home/alexzhao/PolyJarvis")
sys.path.insert(0, str(REPO / "orchestration" / "scripts"))
import workflow_engine as we  # noqa: E402

def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

anchors = {i: REPO / "data" / f"PEG_{i}" / "workflow_state.json" for i in (1, 2, 3)}
before = {i: sha(p) for i, p in anchors.items()}

for i in (1, 2, 3):
    run = f"PEG_COMPASS_{i}"
    run_dir = REPO / "data" / run
    assert run_dir.name.startswith("PEG_COMPASS_"), run_dir
    state_path = run_dir / "workflow_state.json"
    assert not state_path.exists(), f"{state_path} already exists -- refusing"
    plan_path = run_dir / "raw" / "run_plan.json"
    plan = json.loads(plan_path.read_text())
    engine = we.WorkflowEngine(run_dir, plan, None, plan_path=plan_path)
    st = engine.state
    assert st["plan_hash"] == we._canonical_hash(plan)
    st["remedy_counters"]["total"] = we.MAX_AUTOMATIC_REMEDIES
    dp = plan["decided_params"]
    st["replicate_protocol_lock"] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "paired_with": f"PEG_{i}",
        "why": (f"Controlled force-field comparison (reviewer comment 4): {run} must execute PEG_{i}'s "
                "frozen PCFF protocol with preferred_ff=compass as the ONLY change. Any automatic remedy "
                "or agent decision would alter the executed protocol (extra continuations, changed "
                "parameters) and break the pairing, so the run is locked exactly like the rev2 "
                "replicates: every automatic remedy is refused and gate verdicts are recorded, not acted on."),
        "mechanism": {
            "remedy_counters.total": we.MAX_AUTOMATIC_REMEDIES,
            "MAX_AUTOMATIC_REMEDIES": we.MAX_AUTOMATIC_REMEDIES,
            "env": {"POLYJARVIS_GATES_ADVISORY": "1"},
            "recovery_agent": None,
            "launch": f"agent_api.py resume {run} (no --recovery-agent-command)",
        },
        "consequence": ("A process failure is not retried: _apply_remedy declines at the total cap and "
                        "_escalate returns escalation_required (no_recovery_agent_configured)."),
        "only_change": {"preferred_ff": ["pcff", "compass"]},
        "pinned_seeds": {"emc_seed": dp["emc_seed"], "velocity_seed": dp["velocity_seed"],
                         "source": f"PEG_{i} emc_build.log -seed= and equilibration 'velocity all create'"},
    }
    engine._save()
    saved = json.loads(state_path.read_text())
    print(run, "stages:", list(saved["stages"]), "plan_hash ok:",
          saved["plan_hash"] == we._canonical_hash(json.loads(plan_path.read_text())),
          "remedy total:", saved["remedy_counters"]["total"],
          "lock:", "replicate_protocol_lock" in saved)

after = {i: sha(p) for i, p in anchors.items()}
print("PEG_1..3 workflow_state unchanged:", before == after)
