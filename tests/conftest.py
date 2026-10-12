"""Suite-wide safety net: a test must never be able to spend money or reach a GPU.

The LangGraph driver's two model nodes shell out to `claude -p`. A test that forgets to
stub a node does not fail -- it silently runs the real thing, takes minutes, and bills a
real budget. That happened once while these tests were being written, which is why the
guard is here rather than in any individual test file.

Any test that legitimately exercises the headless path stubs `subprocess.run` itself and is
unaffected; this only catches the calls nobody meant to make.
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "orchestration" / "scripts"))


@pytest.fixture(autouse=True)
def _never_invoke_a_real_model(monkeypatch, request):
    """Make an unstubbed `claude -p` call a loud test failure instead of a real spend."""
    if request.node.get_closest_marker("allow_headless_claude"):
        return
    try:
        import headless_claude
    except ImportError:
        return

    def refuse(*args, **kwargs):
        raise AssertionError(
            "a test tried to invoke a real headless `claude -p` session. Stub the node "
            "(or headless_claude.invoke) instead -- see tests/conftest.py."
        )

    monkeypatch.setattr(headless_claude, "invoke_once", refuse)
    monkeypatch.setattr(headless_claude, "invoke", refuse)


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "allow_headless_claude: test deliberately exercises the real `claude -p` path")


@pytest.fixture(autouse=True)
def _no_resource_wait(monkeypatch):
    """Never wait out a real resource deadline inside the test suite.

    workflow_engine._apply_remedy waits RESOURCE_WAIT_S (20 min in production) for a GPU or
    disk to come free before letting a blocked transient_retry escalate -- because escalating
    spends one of only two recovery-agent calls, which is what killed PE_1 on 2026-09-11. That
    wait consults the REAL GPU ledger, so on a busy box the engine tests inherited a 20-minute
    stall each. The production default stays where it belongs; the suite asks the predicate
    only for its verdict.
    """
    import workflow_engine
    monkeypatch.setattr(workflow_engine, "RESOURCE_WAIT_S", 0.0, raising=False)
