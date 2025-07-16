FROM apache/airflow:2.11.0-python3.12

# Build arguments for PyPI server authentication
ARG PYPI_SERVER_USERNAME
ARG PYPI_SERVER_PASSWORD
ARG AIRFLOW_VERSION=2.11.0
ARG PYTHON_VERSION=3.12

USER airflow

# Set up working directory in Airflow's expected location
WORKDIR /opt/airflow

# Set uv environment variables for authentication
ENV UV_INDEX_HOMELAB_USERNAME=${PYPI_SERVER_USERNAME} \
    UV_INDEX_HOMELAB_PASSWORD=${PYPI_SERVER_PASSWORD}

# Copy all project files
COPY --chown=airflow:root . .

# Install dependencies from pyproject.toml without disrupting the base environment
RUN --mount=type=cache,target=/home/airflow/.cache/uv \
    uv pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -e .

# Set up Airflow directories with symbolic links
RUN ln -sf /opt/airflow/homelab_airflow_dags/dags /opt/airflow/dags && \
    ln -sf /opt/airflow/homelab_airflow_dags/config /opt/airflow/config && \
    ln -sf /opt/airflow/homelab_airflow_dags/plugins /opt/airflow/plugins
