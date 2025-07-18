FROM apache/airflow:2.11.0-python3.12

# Build arguments for PyPI server authentication
ARG PYPI_SERVER_USERNAME
ARG PYPI_SERVER_PASSWORD
ARG AIRFLOW_VERSION=2.11.0
ARG PYTHON_VERSION=3.12

USER airflow

# Set up working directory in /app first
WORKDIR /app

# Set uv environment variables for authentication
ENV UV_INDEX_HOMELAB_USERNAME=${PYPI_SERVER_USERNAME} \
    UV_INDEX_HOMELAB_PASSWORD=${PYPI_SERVER_PASSWORD}

# Copy all project files to /app
COPY --chown=airflow:root . .

# Install dependencies from pyproject.toml without disrupting the base environment
RUN --mount=type=cache,target=/home/airflow/.cache/uv \
    uv pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -e . 

# Switch to Airflow's expected location and set up symbolic links
WORKDIR /opt/airflow
RUN ln -sf /app/homelab_airflow_dags/dags /opt/airflow/dags && \
    ln -sf /app/homelab_airflow_dags/config /opt/airflow/config && \
    ln -sf /app/homelab_airflow_dags/plugins /opt/airflow/plugins
