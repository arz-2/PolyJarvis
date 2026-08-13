"""gen_prompt.py --out — writes the prompt to disk and prints only its path.

Keeps the prompt body (4-10 kB per spawn) out of the orchestrator's context.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
GEN_PROMPT = REPO_ROOT / "orchestration" / "scripts" / "gen_prompt.py"
RUN_NAME = "_gen_prompt_out_test"
RUN_DIR = REPO_ROOT / "data" / RUN_NAME

STAGES = ["build", "equil", "equil-check", "tg", "murnaghan", "analyze-bm"]


@pytest.fixture(autouse=True)
def clean_run_dir():
    shutil.rmtree(RUN_DIR, ignore_errors=True)
    yield
    shutil.rmtree(RUN_DIR, ignore_errors=True)


def gen(*extra):
    return subprocess.run(
        [sys.executable, str(GEN_PROMPT), "--run_name", RUN_NAME,
         "--polymer_class", "PACR", *extra],
        capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT),
    )


@pytest.mark.parametrize("stage", STAGES)
def test_out_prints_one_path_holding_the_same_prompt(stage):
    with_out = gen("--stage", stage, "--out")
    assert with_out.returncode == 0, with_out.stderr

    lines = with_out.stdout.splitlines()
    assert len(lines) == 1, f"stdout must be exactly the path, got: {lines}"

    path = Path(lines[0])
    assert path.is_absolute() and path.is_file()
    assert path.parent == RUN_DIR / "raw" / "prompts", "must live under data/**, which the " \
        "context-boundary allowlist already grants every worker"

    direct = gen("--stage", stage)
    assert path.read_text() == direct.stdout.rstrip("\n")


def test_identical_args_reuse_one_file():
    first = gen("--stage", "equil", "--out").stdout.strip()
    second = gen("--stage", "equil", "--out").stdout.strip()
    assert first == second
    assert len(list((RUN_DIR / "raw" / "prompts").glob("equil-*.txt"))) == 1


def test_repeated_stages_get_distinct_files():
    """The same stage is spawned more than once per campaign — tg per rate, equil per phase."""
    r0 = gen("--stage", "tg", "--tg_rate_index", "0", "--out").stdout.strip()
    r1 = gen("--stage", "tg", "--tg_rate_index", "1", "--out").stdout.strip()
    assert r0 != r1

    melt = gen("--stage", "equil", "--phase", "melt", "--out").stdout.strip()
    cooldown = gen("--stage", "equil", "--phase", "cooldown", "--out").stdout.strip()
    assert melt != cooldown


def test_without_out_nothing_is_written():
    r = gen("--stage", "equil")
    assert r.returncode == 0
    assert len(r.stdout.splitlines()) > 1
    assert not RUN_DIR.exists()


def test_out_requires_run_name():
    r = subprocess.run(
        [sys.executable, str(GEN_PROMPT), "--stage", "equil", "--polymer_class", "PACR", "--out"],
        capture_output=True, text=True, timeout=120, cwd=str(REPO_ROOT),
    )
    assert r.returncode != 0
    assert "--run_name" in r.stderr
