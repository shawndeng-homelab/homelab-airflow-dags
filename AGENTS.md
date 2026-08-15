# Repository Guidelines

## Project Structure & Module Organization

This is a `uv` workspace. The main package lives in `packages/homelab-airflow-dags/` and exposes Airflow code under `src/homelab_airflow_dags/`.

- `src/homelab_airflow_dags/dags/`: DAG definitions, such as `ibkr_account_snapshot.py`
- `src/homelab_airflow_dags/common_tasks/`: shared task helpers and operators
- `src/homelab_airflow_dags/config.py`, `constants.py`: runtime config and shared values
- `tests/`: pytest-based tests for the package
- `docs/`: MkDocs documentation source
- `docker/`: local Airflow stack and container files

Keep new DAGs and helpers inside the package source tree; keep tests alongside the package under `tests/`.

## Build, Test, and Development Commands

Use `just` for day-to-day work:

- `just init`: install workspace dependencies and pre-commit hooks
- `just lint`: run Ruff fix, format, and lint checks
- `just test`: run the test suite for the default Python version
- `just test-all`: run tests across the configured Python version range
- `just docs`: serve the documentation locally
- `just docs-build`: build the static docs site
- `just podman-compose-up` / `just podman-compose-down`: start or stop the local Airflow stack

If `just` is not installed, the README uses `uvx --from rust-just just ...`.

## Coding Style & Naming Conventions

Target Python 3.12. Follow the existing Ruff-driven style: standard formatting, sorted imports, and no extra lint suppressions unless necessary. Use `snake_case` for modules, functions, and variables; use descriptive DAG and task names. Keep helper modules small and purpose-driven.

## Testing Guidelines

Tests use `pytest` with coverage enabled through the `just` recipes. Name test files `test_*.py` and keep fixtures in `conftest.py` when they are shared. Add or update tests whenever DAG behavior, config parsing, or shared helpers change.

## Commit & Pull Request Guidelines

Recent commits use short conventional prefixes such as `fix:`, `refactor:`, `style:`, and `chore(version):`. Keep commit subjects imperative and scoped.

Pull requests should include:

- a short summary of the change and why it exists
- validation steps run locally, such as `just lint` and `just test`
- linked issues or follow-up tasks when relevant
- screenshots only for doc or UI-visible changes

## Security & Configuration Tips

This project resolves runtime configuration through Consul-backed settings. Do not commit secrets, tokens, or environment-specific values; prefer local environment variables or documented config files.
