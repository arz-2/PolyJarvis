"""Tests for the P0b suggestion engine (aggregate + propose_diff).

RunRecords are built programmatically so these stay independent of the P0a
markdown fixtures (and their corpus-count assertions).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.runlog_miner import aggregate, extract_signals, propose_diff  # noqa: E402
from tools.runlog_miner.parse import Decision, Recovery, RunRecord  # noqa: E402


def _pcbn_run(name, density=None, tstart=None, anneal=False, finite_size=False):
    recs = []
    if density is not None:
        recs.append(Recovery(
            stage="2", trigger="EXTEND×2 density drift",
            diagnosis="density_initial too close to RT density; over-densified trap",
            fix=f"restarted compress with density_initial={density}"
                + ("; added one extra annealing cycle" if anneal else ""),
            outcome="converged — density drift 0.7%; PASS at Stage 2",
        ))
    if tstart is not None:
        recs.append(Recovery(
            stage="3", trigger="extract_tg <4 bins",
            diagnosis="T_START below MD Tg; glassy slope missing",
            fix=f"re-ran sweep with T_START={tstart}K",
            outcome="converged — R²=0.94",
        ))
    decisions = {"D-01": Decision("PCFF", "classify_polymer returned PCBN → EMC PCFF", True)}
    if finite_size:
        decisions["D-04"] = Decision("DP=40, 10 chains", "finite-size: longer DP needed", True)
    return RunRecord(run_name=name, polymer_class="PCBN", ff="PCFF",
                     decisions=decisions, recoveries=recs)


_RULES = {"classes": {"PCBN": {
    "density_initial_gcm3": 0.60,
    "tg_t_high_K": 700,
    "eq_annealing_cycles": 5,
    "dp_typical": 40,
}}}


def _write_rules(tmp_path):
    p = tmp_path / "polymer_rules.json"
    p.write_text(json.dumps(_RULES, indent=2), encoding="utf-8")
    return p


def test_extract_density_and_tstart_signals():
    sig = extract_signals(_pcbn_run("R", density=0.55, tstart=750))
    fields = {(s.field, s.value) for s in sig}
    assert ("density_initial_gcm3", 0.55) in fields
    assert ("tg_t_high_K", 750.0) in fields


def test_failed_recovery_yields_no_signal():
    r = _pcbn_run("R", density=0.55)
    r.recoveries[0].outcome = "failed again — still drifting"
    assert extract_signals(r) == []


def test_min_support_gate():
    classes = _RULES["classes"]
    one = aggregate([_pcbn_run("PC1", density=0.55)], classes, min_support=2)
    assert one == {}                              # 1 run < 2 → nothing
    two = aggregate(
        [_pcbn_run("PC1", density=0.55), _pcbn_run("PC2", density=0.54)],
        classes, min_support=2,
    )
    assert two["PCBN"]["density_initial_gcm3"]["suggested"] == 0.545
    assert two["PCBN"]["density_initial_gcm3"]["current"] == 0.60
    assert sorted(two["PCBN"]["density_initial_gcm3"]["support_runs"]) == ["PC1", "PC2"]


def test_no_suggestion_when_equal_to_current():
    # both runs converge at exactly the current default → no-op, nothing proposed
    out = aggregate(
        [_pcbn_run("PC1", density=0.60), _pcbn_run("PC2", density=0.60)],
        _RULES["classes"], min_support=2,
    )
    assert out == {}


def test_review_flags_have_null_suggestion():
    out = aggregate(
        [_pcbn_run("PC1", density=0.55, anneal=True, finite_size=True),
         _pcbn_run("PC2", density=0.54, anneal=True, finite_size=True)],
        _RULES["classes"], min_support=2,
    )
    assert out["PCBN"]["eq_annealing_cycles"]["suggested"] is None
    assert out["PCBN"]["dp_typical"]["suggested"] is None


def test_propose_diff_changes_only_suggested_fields(tmp_path):
    rules_path = _write_rules(tmp_path)
    runs = [_pcbn_run("PC1", density=0.55, tstart=750),
            _pcbn_run("PC2", density=0.54, tstart=750)]
    suggestions = aggregate(runs, _RULES["classes"], min_support=2)
    diff = propose_diff(rules_path, suggestions)
    assert '-      "density_initial_gcm3": 0.6,' in diff
    assert '+      "density_initial_gcm3": 0.545,' in diff
    assert '-      "tg_t_high_K": 700,' in diff
    assert '+      "tg_t_high_K": 750,' in diff
    # untouched field may appear as diff context, but never as a +/- change line
    changed = [l for l in diff.splitlines()
               if l[:1] in "+-" and not l.startswith(("+++", "---"))]
    assert not any("dp_typical" in l for l in changed)


def test_propose_diff_empty_when_no_numeric(tmp_path):
    rules_path = _write_rules(tmp_path)
    # review-only signals → no numeric diff
    runs = [_pcbn_run("PC1", finite_size=True), _pcbn_run("PC2", finite_size=True)]
    suggestions = aggregate(runs, _RULES["classes"], min_support=2)
    assert propose_diff(rules_path, suggestions) == ""
