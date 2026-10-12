# Repository Guidelines

## Project Structure & Module Organization

PolyJarvis is a deterministic polymer molecular-dynamics platform. The agent-facing contract, campaign runner, parameter resolution, and protocol policy live in `orchestration/scripts/`. Machine-readable polymer configuration stays in `guides/polymer_rules.json`; human documentation belongs in `docs/`. Builder, LAMMPS, parser, and analysis implementations live under `mcp-servers/`. Treat `data/<run_name>/` as generated per-run workspace. Agents must not write simulation files or own runtime state.

## Build, Test, and Development Commands

Create a lightweight test environment with:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-test.txt
```

Run `pytest -v` for the default pure-logic suite; `pytest.ini` automatically excludes tests requiring EMC, LAMMPS, or RadonPy. Run a focused test with `pytest tests/test_protocol_policy.py -v`. Use `pytest -m requires_binaries` only on a configured simulation host. Preview hardware calibration safely with `python3 hardware/calibrate_hardware.py --dry-run`.

## Coding Style & Naming Conventions

Follow existing Python conventions: four-space indentation, `snake_case` for functions/modules, `UPPER_CASE` for constants, and descriptive CLI option names. Keep scripts import-safe where practical and put executable behavior behind `if __name__ == "__main__":`. Add type hints and concise docstrings when interfaces or scientific assumptions are not obvious. No repository-wide formatter is configured, so match adjacent code and keep diffs focused. Preserve established JSON schemas and template placeholders; orchestration files are runtime contracts, not prose-only configuration.

## Testing Guidelines

Use pytest and name files `test_<behavior>.py` and tests `test_<expected_behavior>`. Place tests beside the relevant subsystem (`tests/`, `mcp-servers/*/tests/`, or `tools/runlog_miner/tests/`). Mark any test that invokes external simulation software with `@pytest.mark.requires_binaries`. Add regression tests for policy, schema, routing, parsing, and deterministic-plan changes. There is no stated coverage threshold; prioritize meaningful branch and failure-mode coverage.

## Commit & Pull Request Guidelines

Recent history favors imperative, scoped subjects such as `chore: ...`, `ingest: ...`, or direct summaries like `Move ...`. Keep each commit cohesive and explain scientific or policy rationale in the body when needed. Pull requests should summarize behavior changes, identify affected tracks/services, list exact test commands and results, and link relevant issues. Include screenshots only for figure or documentation-rendering changes; include representative generated-plan or analysis output for schema-sensitive changes, without committing large run artifacts.

## Security & Configuration

Keep machine-specific paths, credentials, `.env`, GPU claims, and generated simulation data out of commits. Use placeholders in documentation and preserve the repository’s gitignored local configuration model.
