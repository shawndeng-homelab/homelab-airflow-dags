FROM apache/airflow:2.11.0-python3.12

ENV AIRFLOW_VERSION=2.11.0 \
    PYTHON_VERSION=3.12 \
    CONSTRAINT_URL=https://raw.githubusercontent.com/apache/airflow/constraints-2.11.0/constraints-3.12.txt

USER root
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
         vim \
  && apt-get autoremove -yqq --purge \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*

USER airflow

WORKDIR /tmp/homelab-airflow-dags
COPY --chown=airflow:root . /tmp/homelab-airflow-dags
RUN uv pip install -e /tmp/homelab-airflow-dags
WORKDIR /opt/airflow
RUN rm -rf /opt/airflow/dags \
  && ln -s /tmp/homelab-airflow-dags/homelab_airflow_dags/dags /opt/airflow/dags \
  && ln -s /tmp/homelab-airflow-dags/homelab_airflow_dags/config /opt/airflow/config \
  && ln -s /tmp/homelab-airflow-dags/homelab_airflow_dags/plugins /opt/airflow/plugins \