import subprocess
import sys
from datetime import datetime
from datetime import timedelta

import airflow
from airflow import DAG
from airflow.operators.python import PythonOperator


default_args = {
    "owner": "admin",
    "depends_on_past": False,
    "email_on_failure": True,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

dag = DAG(
    "update_dependencies_uv_constraints_simple",
    default_args=default_args,
    description="使用uv和约束文件更新依赖（简洁版）",
    schedule_interval="@daily",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["dependencies"],
)


def update_with_uv_and_constraints():
    """使用uv和约束文件更新依赖"""  # noqa: D415
    # URL配置
    requirements_url = (
        "https://raw.githubusercontent.com/shawndeng-homelab/homelab-airflow-dags/master/requirements.txt"
    )

    # 自动构建约束文件URL
    python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    airflow_version = airflow.__version__
    constraints_url = f"https://raw.githubusercontent.com/apache/airflow/constraints-{airflow_version}/constraints-{python_version}.txt"

    print(f"Python版本: {python_version}")
    print(f"Airflow版本: {airflow_version}")
    print(f"约束文件: {constraints_url}")

    # 确保uv已安装
    try:
        subprocess.run(["uv", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("安装uv...")
        subprocess.run([sys.executable, "-m", "pip", "install", "uv"], check=True)

    # 构建命令
    cmd = ["uv", "pip", "install", "-r", requirements_url, "--constraint", constraints_url, "--upgrade", "--user"]

    print(f"\n执行命令: {' '.join(cmd)}")

    # 执行安装
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout:
        print("\n输出:")
        print(result.stdout)

    if result.stderr:
        print("\n错误/警告:")
        print(result.stderr)

    if result.returncode != 0:
        raise Exception(f"依赖更新失败，返回码: {result.returncode}")

    # 显示结果
    print("\n=== 更新完成，当前主要包版本 ===")
    list_cmd = ["uv", "pip", "list", "--format", "freeze"]
    list_result = subprocess.run(list_cmd, capture_output=True, text=True)

    # 只显示一些关键包
    for line in list_result.stdout.split("\n"):
        if any(pkg in line.lower() for pkg in ["airflow", "pandas", "numpy", "sqlalchemy", "celery"]):
            print(line)


# 单一任务
update_task = PythonOperator(
    task_id="update_dependencies",
    python_callable=update_with_uv_and_constraints,
    dag=dag,
)
