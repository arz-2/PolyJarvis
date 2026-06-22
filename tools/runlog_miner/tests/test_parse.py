"""Golden-fixture tests for runlog_miner P0a (parse + report)."""
import sys
from pathlib import Path

import pytest

# repo root = tools/runlog_miner/tests/ -> parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.runlog_miner import load_corpus, parse_run_log, summarize  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="module")
def pc1():
    return parse_run_log(FIXTURES / "PC1" / "run_log.md")


@pytest.fixture(scope="module")
def pc2():
    return parse_run_log(FIXTURES / "PC2" / "run_log.md")


def test_header_and_routing_fields(pc1):
    assert pc1.polymer_name == "BPA-PC"
    assert pc1.polymer_class == "PCBN"
    assert pc1.ff == "PCFF"
    assert pc1.charge_method == "embedded in FF"
    assert pc1.dp == 40
    assert pc1.n_chains == 10
    assert pc1.n_atoms == 13120
    assert pc1.smiles.startswith("*Oc1ccc")


def test_decisions_parsed(pc1):
    assert pc1.decisions["D-01"].value == "PCFF"
    assert pc1.convergence == "PASS"
    assert pc1.fit_quality == "ACCEPTABLE"
    assert all(d.filled for d in pc1.decisions.values())


def test_clean_run_has_no_recoveries_and_ignores_comment_example(pc1):
    # the [Stage 9] block lives inside an HTML comment and must be stripped
    assert pc1.has_recoveries is False
    assert pc1.recoveries == []
    assert not pc1.warnings  # clean parse


def test_results_parsed(pc1):
    assert pc1.results["Tg"].computed == "528 K"
    assert pc1.results["Tg"].experimental == "422 K"
    assert pc1.results["Tg"].error == "25%"
    assert pc1.results["rho"].computed == "1.19 g/cm³"
    assert pc1.results["Tg"].filled is True


def test_recoveries_parsed(pc2):
    assert len(pc2.recoveries) == 2
    first, second = pc2.recoveries
    assert first.stage == "2"
    assert "density_initial" in first.diagnosis
    assert "density_initial=0.55" in first.fix
    assert first.outcome.startswith("converged")
    assert second.stage == "3"
    assert "below MD Tg" in second.diagnosis


def test_load_corpus_skips_template():
    records = load_corpus(FIXTURES, "*/run_log.md")
    names = {r.run_name for r in records}
    assert names == {"PC1", "PC2"}  # TEMPLATE excluded


def test_summarize_runs_without_error():
    records = load_corpus(FIXTURES, "*/run_log.md")
    md = summarize(records)
    assert "run_log corpus summary" in md
    assert "PCBN" in md
    assert "runs with recoveries: **1**" in md
    assert "## Recoveries" in md


def test_to_dict_is_json_safe(pc2):
    import json

    json.dumps(pc2.to_dict())  # must not raise
