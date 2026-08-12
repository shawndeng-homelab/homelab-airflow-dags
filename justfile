set dotenv-load := true
set shell := ["bash", "-euc"]
set windows-shell := ["powershell.exe", "-NoLogo", "-NoProfile", "-Command"]

package_name := "homelab_airflow_dags"
python_min_version := "3.12"
python_max_version := "3.12"
python_dev_version := python_min_version
pypi_server_url := "https://pypiserver.shawndeng.cc"

# Show available recipes
default:
    @just --list

# Sync workspace deps and install pre-commit hooks
init:
    uv tool install rust-just
    uv sync --all-packages --all-groups
    uvx pre-commit install

# Run ruff fix + format + check
lint:
    uvx ruff check --fix .
    uvx ruff format .
    uvx ruff check .

# Add `# noqa` for current violations, then re-run lint
lint-add-noqa: && lint-pre-commit lint
    uvx ruff check --add-noqa .

# Run all pre-commit hooks against the whole tree
lint-pre-commit:
    uvx pre-commit run --all-files

# Watch and re-run ruff on changes
lint-watch:
    uvx ruff check --watch .

# Run tests with the dev Python version
test:
    @just test-version {{python_dev_version}}

# Run tests across the configured Python version range
test-all:
    uv run python -c "import subprocess; mn=int('{{python_min_version}}'.split('.')[1]); mx=int('{{python_max_version}}'.split('.')[1]); [subprocess.check_call(['uv','run','--all-packages','--all-groups','--python',f'3.{m}','pytest','--cov={{package_name}}','--cov-report=xml','--cov-report=term-missing','-v','packages/']) for m in range(mn, mx + 1)]"

# Run tests for a specific Python version
test-version version:
    uv run --all-packages --all-groups --python {{version}} pytest --cov={{package_name}} --cov-report=xml --cov-report=term-missing -v packages/

# Serve docs locally
docs:
    uv run --all-packages --group docs mkdocs serve

# Build static docs
docs-build:
    uv run --all-packages --group docs mkdocs build

# Deploy docs to GitHub Pages
deploy-gh-pages:
    uv run --all-packages --group docs mkdocs gh-deploy --force

# Build sdist + wheel for every workspace package
build:
    uv build --all-packages

# Build only packages that have a new version tag (for CI)
build-changed:
    #!/usr/bin/env bash
    set -euo pipefail
    # Get the commit this workflow is running on
    commit=$(git rev-parse HEAD)
    built=0
    for pkg_dir in packages/*/; do
        pkg=$(basename "$pkg_dir")
        # Read version from pyproject.toml
        ver=$(grep '^version' "$pkg_dir/pyproject.toml" | head -1 | sed 's/version.*=.*"\(.*\)"/\1/')
        tag="${pkg}-${ver}"
        # Only build if the tag exists AND points to the current commit
        if tag_commit=$(git rev-parse "refs/tags/${tag}^{commit}" 2>/dev/null) && [ "$tag_commit" = "$commit" ]; then
            echo "✅ ${pkg} ${ver} has new tag at this commit, building..."
            uv build --package "$pkg"
            built=$((built + 1))
        else
            echo "⏭️  ${pkg} ${ver} tag not at this commit, skipping"
        fi
    done
    if [ "$built" -eq 0 ]; then
        echo "No changed packages to build"
    fi

# Publish to public PyPI (skip packages whose version already exists)
publish-pypi:
    uv publish --check-url https://pypi.org/simple/

# Publish to the private PyPI server (skip packages whose version already exists)
publish-pypi-server:
    uv publish --username {{env_var('PYPI_SERVER_USERNAME')}} --password {{env_var('PYPI_SERVER_PASSWORD')}} --publish-url {{env_var_or_default('PYPI_SERVER_URL', pypi_server_url)}} --check-url {{env_var_or_default('PYPI_SERVER_URL', pypi_server_url)}}/simple/

# Publish to both indexes
publish-all: publish-pypi publish-pypi-server

# Build then publish to public PyPI
deploy-pypi: build publish-pypi

# Build then publish to the private server
deploy-pypi-server: build publish-pypi-server

# Build then publish to both indexes
deploy-all: build publish-all

# Export pinned deps to requirements.txt
export-deps:
    uv export --no-hashes --output-file requirements.txt

# Add a new package to the workspace (creates package dir + updates cog.toml + syncs)
add-package name:
    repo-scaffold add-package {{name}}

# Bring up the local CeleryExecutor Airflow stack (postgres + redis) via podman compose
podman-compose-up:
    podman compose -f docker/docker-compose.yaml up -d

# Tear down the local Airflow stack
podman-compose-down:
    podman compose -f docker/docker-compose.yaml down
