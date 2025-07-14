FROM apache/airflow:2.11.0-python3.12

# Build arguments for PyPI server authentication
ARG PYPI_SERVER_USERNAME
ARG PYPI_SERVER_PASSWORD
ARG PYPI_SERVER_URL
ARG AIRFLOW_VERSION=2.11.0
ARG PYTHON_VERSION=3.12

ENV AIRFLOW_VERSION=${AIRFLOW_VERSION} \
    PYTHON_VERSION=${PYTHON_VERSION} \
    CONSTRAINT_URL=https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt

# Install uv
USER root
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
         vim \
  && apt-get autoremove -yqq --purge \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

USER airflow

# Set uv environment variables for authentication and constraints
ENV UV_INDEX_HOMELAB_USERNAME=${PYPI_SERVER_USERNAME} \
    UV_INDEX_HOMELAB_PASSWORD=${PYPI_SERVER_PASSWORD} \
    UV_CONSTRAINT=https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app

# Copy dependency files first for better caching
COPY --chown=airflow:root pyproject.toml uv.lock ./

# Install dependencies only (without the project itself)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project

# Copy the project source code
COPY --chown=airflow:root . .

# Install the project itself (non-editable to avoid build issues)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable

# Set up Airflow directories
WORKDIR /opt/airflow
RUN rm -rf /opt/airflow/dags \
  && ln -s /app/homelab_airflow_dags/dags /opt/airflow/dags \
  && ln -s /app/homelab_airflow_dags/config /opt/airflow/config \
  && ln -s /app/homelab_airflow_dags/plugins /opt/airflow/plugins

# Activate the virtual environment
ENV PATH="/app/.venv/bin:$PATH"
