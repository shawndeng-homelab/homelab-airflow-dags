FROM apache/airflow:3.2.0-python3.12

# Build arguments for platform detection
ARG TARGETPLATFORM

# Build arguments for PyPI server authentication
ARG PYPI_SERVER_USERNAME
ARG PYPI_SERVER_PASSWORD
ARG AIRFLOW_VERSION=3.2.0
ARG PYTHON_VERSION=3.12

# Build arguments for Consul configuration
ARG CONSUL_HOST
ARG CONSUL_PORT=443
ARG CONSUL_TOKEN

# 使用 root 用户进行构建和文件操作
USER root

# Install build dependencies for compiling Python packages with C extensions
# Always install git to support pip/virtualenv requirements
RUN apt-get update && \
    apt-get install -y git && \
    if [ "$TARGETPLATFORM" = "linux/arm64" ]; then \
        apt-get install -y build-essential gcc g++; \
    fi && \
    rm -rf /var/lib/apt/lists/*

# Set up working directory in /app first
WORKDIR /app

# Set uv environment variables for authentication against the private homelab index.
# UV_INDEX_HOMELAB_* authenticate the index named "homelab" passed via --index below.
ENV UV_INDEX_HOMELAB_USERNAME=${PYPI_SERVER_USERNAME} \
    UV_INDEX_HOMELAB_PASSWORD=${PYPI_SERVER_PASSWORD} \
    CONSUL_HOST=${CONSUL_HOST} \
    CONSUL_PORT=${CONSUL_PORT} \
    CONSUL_TOKEN=${CONSUL_TOKEN}

# Copy all project files to /app
COPY . .

# Install the workspace member (editable) into the Airflow environment.
# The base image already ships apache-airflow==3.2.0; the pin is defensive.
# The homelab index is declared explicitly so private deps (homelab-config,
# and the runtime ibkr-quant) resolve from it. unsafe-best-match searches
# all indexes so PyPI-only and homelab-only packages both resolve.
RUN --mount=type=cache,target=/root/.cache/uv \
    UV_INDEX_STRATEGY=unsafe-best-match \
    uv pip install --no-cache-dir \
    --index "homelab=https://pypiserver.shawndeng.cc/simple" \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -e packages/homelab-airflow-dags

# Switch to Airflow's expected location and set up symbolic links.
# Only dags exists in the package; config/plugins dirs are not shipped.
WORKDIR /opt/airflow
RUN ln -sf /app/packages/homelab-airflow-dags/src/homelab_airflow_dags/dags /opt/airflow/dags && \
    ln -sf /app/packages/homelab-airflow-dags/src/homelab_airflow_dags /opt/airflow/homelab_airflow_dags

# 确保 airflow 用户拥有必要的权限
RUN chown -R airflow:root /app /opt/airflow

# 最后切换回 airflow 用户
USER airflow
