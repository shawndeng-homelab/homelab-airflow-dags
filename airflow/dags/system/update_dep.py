from datetime import datetime
from datetime import timedelta

from airflow import DAG
from airflow.operators.bash import BashOperator


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


bash_command = """
set -e

# 设置变量
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
AIRFLOW_VERSION=$(python3 -c 'import airflow; print(airflow.__version__)')

REQUIREMENTS_URL="https://raw.githubusercontent.com/shawndeng-homelab/homelab-airflow-dags/master/requirements.txt"
CONSTRAINTS_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

echo "Python版本: ${PYTHON_VERSION}"
echo "Airflow版本: ${AIRFLOW_VERSION}"
echo "约束文件: ${CONSTRAINTS_URL}"

# 下载 requirements.txt 到临时文件
TEMP_REQ="/tmp/requirements_$$.txt"
curl -sL "${REQUIREMENTS_URL}" -o "${TEMP_REQ}"

# 下载 constraints.txt 到临时文件
TEMP_CONST="/tmp/constraints_$$.txt"
curl -sL "${CONSTRAINTS_URL}" -o "${TEMP_CONST}"

# 使用 pip 安装
echo "开始安装依赖..."
python3 -m pip install -r "${TEMP_REQ}" --constraint "${TEMP_CONST}" --upgrade --user || \
python3 -m pip install -r "${TEMP_REQ}" --constraint "${TEMP_CONST}" --upgrade

# 清理临时文件
rm -f "${TEMP_REQ}" "${TEMP_CONST}"

# 显示安装结果
echo ""
echo "=== 更新完成，当前主要包版本 ==="
python3 -m pip list --format freeze | grep -iE "(airflow|pandas|numpy|sqlalchemy|celery)" || true
"""

update_task = BashOperator(
    task_id="update_dependencies",
    bash_command=bash_command,
    dag=dag,
)
