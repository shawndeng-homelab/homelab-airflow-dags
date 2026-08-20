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

COPY . .

# Install all workspace members discovered from packages/*/pyproject.toml.
# The official base image provides Airflow's runtime environment; workspace metadata supplies project dependencies.
RUN --mount=type=cache,target=/root/.cache/uv \
    set -- && \
    for package in packages/*; do \
        if [ -f "$package/pyproject.toml" ]; then \
            set -- "$@" -e "$package"; \
        fi; \
    done && \
    UV_INDEX_HOMELAB_USERNAME="${PYPI_SERVER_USERNAME}" \
    UV_INDEX_HOMELAB_PASSWORD="${PYPI_SERVER_PASSWORD}" \
    UV_INDEX_STRATEGY=unsafe-best-match \
    uv pip install \
    --index "homelab=https://pypiserver.shawndeng.cc/simple" \
    "$@"

# Replace Airflow's build Git revision in the footer with the version of the
# homelab DAG package that is actually installed in this image.
RUN python -m homelab_airflow_dags.patch_airflow_ui

# Keep Airflow's conventional DAG location in the baked image. Compose mounts
# the live workspace DAG directory over this path during development.
WORKDIR /opt/airflow
RUN mkdir -p /opt/airflow/dags && \
    cp -a /app/packages/homelab-airflow-dags/src/homelab_airflow_dags/dags/. /opt/airflow/dags/ && \
    chown -R airflow:root /app /opt/airflow

USER airflow
