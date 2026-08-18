FROM apache/airflow:2.11.0-python3.12

ARG TARGETPLATFORM
ARG PYPI_SERVER_USERNAME
ARG PYPI_SERVER_PASSWORD

USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    if [ "$TARGETPLATFORM" = "linux/arm64" ]; then \
        apt-get install -y --no-install-recommends build-essential gcc g++; \
    fi && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    AIRFLOW_HOME=/opt/airflow \
    UV_COMPILE_BYTECODE=1

# Copy only workspace metadata first so dependency installation remains cached
# when application source files change.
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    UV_INDEX_HOMELAB_USERNAME="${PYPI_SERVER_USERNAME}" \
    UV_INDEX_HOMELAB_PASSWORD="${PYPI_SERVER_PASSWORD}" \
    UV_INDEX_STRATEGY=unsafe-best-match \
    uv sync --all-packages --frozen --no-default-groups --no-install-workspace

COPY . .

# Install every workspace member in editable mode. The package dependencies,
# including Airflow 2.11.0, are resolved from the shared uv.lock file.
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_INDEX_HOMELAB_USERNAME="${PYPI_SERVER_USERNAME}" \
    UV_INDEX_HOMELAB_PASSWORD="${PYPI_SERVER_PASSWORD}" \
    UV_INDEX_STRATEGY=unsafe-best-match \
    uv sync --all-packages --frozen --no-default-groups

# Keep Airflow's standard DAG location in the baked image. Compose can mount
# the live workspace DAG directory over this path during development.
RUN mkdir -p /opt/airflow/dags && \
    cp -a /app/packages/homelab-airflow-dags/src/homelab_airflow_dags/dags/. /opt/airflow/dags/ && \
    chown -R airflow:root /app /opt/airflow

USER airflow