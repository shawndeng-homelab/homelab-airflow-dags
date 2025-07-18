from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from homelab_airflow_dags.config import get_config


def func():  # noqa: D103
    result = get_config("risk_portfolio_config")
    print(result)
    print("===" * 5)


with DAG(dag_id="test-dag", start_date=datetime(2025, 7, 12), schedule="@daily"):
    PythonOperator(
        task_id="test",
        python_callable=func,
    )
