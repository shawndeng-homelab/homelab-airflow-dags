from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator


def func():  # noqa: D103
    print("hello word")


with DAG(dag_id="test-dag", start_date=datetime(2025, 7, 12), schedule="@daily"):
    PythonOperator(
        task_id="test",
        python_callable=func,
    )
