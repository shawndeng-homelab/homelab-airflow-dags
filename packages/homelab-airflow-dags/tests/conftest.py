"""Pytest configuration shared across the homelab-airflow-dags test suite."""

import os

# Airflow 3 rejects relative sqlite DB paths (AirflowConfigException:
# "Cannot use relative path"). Local dev commonly sets AIRFLOW_HOME=./airflow
# (relative) via .env; resolve it to an absolute path *before* Airflow is
# imported so DAG instantiation during import-tests doesn't fail. CI has no
# .env, so AIRFLOW_HOME already defaults to an absolute path there.
_airflow_home = os.environ.get("AIRFLOW_HOME")
if _airflow_home and not os.path.isabs(_airflow_home):
    os.environ["AIRFLOW_HOME"] = os.path.abspath(_airflow_home)
