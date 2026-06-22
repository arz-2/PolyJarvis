"""Tests for the P0c recovery-playbook clusterer."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tools.runlog_miner import build_playbook, cluster_recoveries  # noqa: E402
from tools.runlog_miner.parse import Recovery, RunRecord  # noqa: E402


def _run(name, cls, recs):
    return RunRecord(run_name=name, polymer_class=cls, recoveries=recs)


_DENSITY = Recovery(stage="2", trigger="EXTEND×2 density drift >2%",
                    diagnosis="density_initial too close to RT density; over-densified trap",
                    fix="restarted compress with density_initial=0.55",
                    outcome="converged — PASS at Stage 2")
_SWEEP = Recovery(stage="3", trigger="extract_tg <4 bins",
                  diagnosis="T_START below MD Tg; glassy slope missing",
                  fix="re-ran sweep with T_START=750K",
                  outcome="converged — R²=0.94")
_LOST = Recovery(stage="2", trigger="LAMMPS error",
                 diagnosis="lost atoms in NPT compress",
                 fix="reduced dt_fs to 0.5",
                 outcome="converged")
_NOVEL = Recovery(stage="1", trigger="EMC weirdness",
                  diagnosis="something nobody has a signature for yet",
                  fix="hand-tuned the esh file",
                  outcome="converged")


def test_clusters_known_signatures():
    clusters, unclustered = cluster_recoveries([_run("PC1", "PCBN", [_DENSITY, _SWEEP])])
    names = {c["name"] for c in clusters}
    assert names == {"density-trap", "sweep-below-Tg"}
    assert unclustered == []
    dens = next(c for c in clusters if c["name"] == "density-trap")
    assert dens["n"] == 1 and dens["k"] == 1
    assert dens["classes"] == ["PCBN"]


def test_success_rate_counts_only_converged():
    failed = Recovery(stage="2", trigger="density drift",
                      diagnosis="density_initial too close",
                      fix="lowered density_initial=0.55",
                      outcome="failed again — still drifting")
    clusters, _ = cluster_recoveries([
        _run("PC1", "PCBN", [_DENSITY]),       # success
        _run("PC2", "PCBN", [failed]),         # not a success
    ])
    dens = next(c for c in clusters if c["name"] == "density-trap")
    assert dens["n"] == 2 and dens["k"] == 1   # k/n = 1/2


def test_unmatched_goes_to_unclustered():
    clusters, unclustered = cluster_recoveries([_run("X1", "PHYC", [_NOVEL])])
    assert clusters == []
    assert len(unclustered) == 1
    assert unclustered[0]["run"] == "X1"


def test_build_playbook_markdown():
    md = build_playbook([_run("PC1", "PCBN", [_DENSITY, _SWEEP, _LOST]),
                         _run("X1", "PHYC", [_NOVEL])])
    assert "# Recovery Playbook" in md
    assert "density-trap" not in md            # name is internal; pattern is shown
    assert "over-densified cell" in md
    assert "1/1" in md                         # density cluster k/n
    assert "PCBN" in md
    assert "## Unclustered incidents" in md
    assert "X1" in md


def test_build_playbook_empty_corpus():
    md = build_playbook([])
    assert "No recovery incidents in the corpus yet" in md
    assert "| Error / symptom pattern |" not in md
