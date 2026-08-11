"""write_d05.py — splices a D-05 block into run_log.md so the payload never transits context."""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "orchestration" / "scripts" / "write_d05.py"
TEMPLATE = REPO_ROOT / "data" / "TEMPLATE" / "run_log.md"

BLOCK = "**Equilibration:** PASS\n\n| Metric | Value |\n|---|---|\n| density drift | 0.4% |"


def run(run_log: Path, d05: Path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--run_log", str(run_log), "--d05", str(d05)],
        capture_output=True, text=True, timeout=60,
    )


def headings(text: str):
    return [ln for ln in text.splitlines() if ln.startswith("#")]


def test_replaces_placeholder_and_preserves_structure(tmp_path):
    run_log = tmp_path / "run_log.md"
    run_log.write_text(TEMPLATE.read_text())
    d05 = tmp_path / "d05_block.md"
    d05.write_text(BLOCK)

    assert run(run_log, d05).returncode == 0

    out = run_log.read_text()
    assert 'Paste result["d05_markdown"]' not in out
    assert "density drift" in out
    assert headings(out) == headings(TEMPLATE.read_text())

    body = out.split("## D-05 CONVERGENCE DETAIL", 1)[1]
    assert body.index("density drift") < body.index("### Chain Structure Summary")


def test_rerun_supersedes_rather_than_appends(tmp_path):
    """An EXTEND re-check replaces its predecessor's block."""
    run_log = tmp_path / "run_log.md"
    run_log.write_text(TEMPLATE.read_text())
    first, second = tmp_path / "a.md", tmp_path / "b.md"
    first.write_text(BLOCK)
    second.write_text("**Equilibration:** PASS (after EXTEND)")

    run(run_log, first)
    run(run_log, second)

    out = run_log.read_text()
    assert out.count("<!-- d05:begin -->") == 1
    assert "after EXTEND" in out
    # the template's D-05 example comment also says "density drift", so key off the table row
    assert "| density drift | 0.4% |" not in out
    assert headings(out) == headings(TEMPLATE.read_text())


def test_errors_on_a_log_without_the_section(tmp_path):
    run_log = tmp_path / "run_log.md"
    run_log.write_text("# Some other file\n")
    d05 = tmp_path / "d05.md"
    d05.write_text(BLOCK)

    r = run(run_log, d05)
    assert r.returncode == 1
    assert "D-05 CONVERGENCE DETAIL" in r.stderr
    assert run_log.read_text() == "# Some other file\n"
