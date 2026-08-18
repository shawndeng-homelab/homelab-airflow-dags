# Repository Guidelines

## Project Structure & Module Organization

- `homelab_airflow_dags/` contains the installable Python package: configuration and constants at the root, reusable Airflow operators/tasks in `common_tasks/`, and DAG definitions in `dags/`.
- `tests/` contains pytest tests; keep tests aligned with the package structure as new modules are added.
- `docs/` contains MkDocs source, with user guidance under `docs/getting-started/`.
- `docker/` contains the image and Compose configuration used to preview Airflow services. CI workflows live in `.github/workflows/`.

## Build, Test, and Development Commands

Use Python 3.12, `uv`, and the repository’s Taskfile. Run `task init` to sync dependencies and install pre-commit hooks. Common commands:

```bash
task lint                 # Ruff autofix, format, and final lint check
task lint:pre-commit      # Run every pre-commit hook
task test                 # Run pytest with coverage on Python 3.12
task test:all             # Run the configured Python-version matrix
task build                # Build wheel and source distribution in dist/
task docs:build           # Build MkDocs documentation
```

For local service validation, use `task podman-compose:up` and `task podman-compose:down`.

## Coding Style & Naming Conventions

Write Python formatted and linted by Ruff, with a 120-character line limit, four-space indentation, Google-style docstrings where applicable, and one import per line. Use `snake_case` for modules, functions, and variables; `PascalCase` for classes; and descriptive DAG/task IDs. Keep configuration examples and YAML consistently formatted with `yamlfmt`.

## Testing Guidelines

Tests use pytest, `pytest-mock`, and `pytest-cov`. Name files `test_*.py` and functions `test_*`. Add regression coverage for changed configuration, operators, and DAG imports; mock external services such as Consul. Run `task test` before submitting changes and ensure the import sweep remains green.

## Commit & Pull Request Guidelines

Use concise Conventional Commit-style subjects such as `feat: ...`, `fix: ...`, `docs: ...`, or `bump: ...`. Keep commits focused. Pull requests should explain the behavior change, identify configuration or deployment impact, link related issues when applicable, and include test/lint results. Include screenshots or rendered documentation examples when changing docs or user-facing workflows.

## Security & Configuration Tips

Copy `.env.example` for local settings and never commit credentials. Private package indexes and publish commands require environment-provided credentials; review `Taskfile.yml` before publishing artifacts.
