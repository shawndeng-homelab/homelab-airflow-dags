import os
import sys
from datetime import datetime
from datetime import timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator


# 测试从 lib 导入
try:
    from fake_useragent import UserAgent
    LIB_IMPORT_SUCCESS = True
except ImportError as e:
    LIB_IMPORT_SUCCESS = False
    print(f"Failed to import from lib: {e}")

# 默认参数
default_args = {
    'owner': 'homelab',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# 定义 DAG
dag = DAG(
    'test_deployment',
    default_args=default_args,
    description='Test DAG for deployment verification',
    schedule_interval=timedelta(hours=1),
    catchup=False,
    tags=['test', 'deployment'],
)


def check_environment(**context):
    """"检查环境变量和 Python 路径"""
    print("=" * 50)
    print("Environment Check")
    print("=" * 50)

    # 检查 Python 路径
    print(f"Python Version: {sys.version}")
    print(f"Python Path: {sys.path}")

    # 检查环境变量
    print(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'Not set')}")
    print(f"AIRFLOW_HOME: {os.environ.get('AIRFLOW_HOME', 'Not set')}")

    # 检查当前工作目录
    print(f"Current Working Directory: {os.getcwd()}")

    # 检查 lib 导入
    print(f"Lib Import Success: {LIB_IMPORT_SUCCESS}")

    return "Environment check completed"


# 任务定义
t1 = BashOperator(
    task_id='print_date',
    bash_command='date',
    dag=dag,
)

t2 = PythonOperator(
    task_id='check_environment',
    python_callable=check_environment,
    dag=dag,
)
