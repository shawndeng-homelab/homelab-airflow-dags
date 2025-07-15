FROM apache/airflow:2.11.0-python3.12

# Build arguments for PyPI server authentication
ARG PYPI_SERVER_USERNAME
ARG PYPI_SERVER_PASSWORD
ARG AIRFLOW_VERSION=2.11.0
ARG PYTHON_VERSION=3.12

USER airflow

# Set up working directory
WORKDIR /app

# Copy project files
COPY --chown=airflow:root . .

# Set uv environment variables for authentication
ENV UV_INDEX_HOMELAB_USERNAME=${PYPI_SERVER_USERNAME} \
    UV_INDEX_HOMELAB_PASSWORD=${PYPI_SERVER_PASSWORD} \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Copy dependency files first for better caching
COPY --chown=airflow:root pyproject.toml uv.lock ./

# Install dependencies using uv with system Python (no virtual environment)
RUN --mount=type=cache,target=/home/airflow/.cache/uv \
    uv sync --locked

# Set up Airflow directories
WORKDIR /opt/airflow
RUN rm -rf /opt/airflow/dags \
  && ln -s /app/homelab_airflow_dags/dags /opt/airflow/dags \
  && ln -s /app/homelab_airflow_dags/config /opt/airflow/config \
  && ln -s /app/homelab_airflow_dags/plugins /opt/airflow/plugins
