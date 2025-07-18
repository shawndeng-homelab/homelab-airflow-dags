FROM apache/airflow:2.11.0-python3.12

# Build arguments for PyPI server authentication
ARG PYPI_SERVER_USERNAME
ARG PYPI_SERVER_PASSWORD
ARG AIRFLOW_VERSION=2.11.0
ARG PYTHON_VERSION=3.12

# Build arguments for Consul configuration
ARG CONSUL_HOST
ARG CONSUL_PORT=443
ARG CONSUL_TOKEN

# 使用 root 用户进行构建和文件操作
USER root

# Install build dependencies for compiling Python packages with C extensions
RUN apt-get update && apt-get install -y \
    build-essential \
    gcc \
    g++ \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set up working directory in /app first
WORKDIR /app

# Set uv environment variables for authentication
ENV UV_INDEX_HOMELAB_USERNAME=${PYPI_SERVER_USERNAME} \
    UV_INDEX_HOMELAB_PASSWORD=${PYPI_SERVER_PASSWORD} \
    CONSUL_HOST=${CONSUL_HOST} \
    CONSUL_PORT=${CONSUL_PORT} \
    CONSUL_TOKEN=${CONSUL_TOKEN}

# Copy all project files to /app
COPY . .

# Install dependencies from pyproject.toml without disrupting the base environment
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --no-cache-dir \
    "apache-airflow==${AIRFLOW_VERSION}" \
    -e . 

# Switch to Airflow's expected location and set up symbolic links
WORKDIR /opt/airflow
RUN ln -sf /app/homelab_airflow_dags/dags /opt/airflow/dags && \
    ln -sf /app/homelab_airflow_dags/config /opt/airflow/config && \
    ln -sf /app/homelab_airflow_dags/plugins /opt/airflow/plugins

# 确保 airflow 用户拥有必要的权限
RUN chown -R airflow:root /app /opt/airflow

# 最后切换回 airflow 用户
USER airflow
