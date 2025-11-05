from datetime import datetime
from datetime import timedelta

from airflow.decorators import dag
from airflow.decorators import task


default_args = {
    "owner": "homelab",
    "depends_on_past": False,
    "start_date": datetime(2025, 1, 1),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="ibkr_account_snapshot",
    default_args=default_args,
    description="IBKR Account Snapshot Data Collection",
    schedule="0 21-23,0-7 * * *",  # 每天晚上9点到次日早上8点,每小时执行
    catchup=False,
    tags=["ibkr", "snapshot", "data-collection"],
)
def ibkr_account_snapshot_dag():
    """IBKR账户快照数据采集DAG."""

    def get_index_urls():
        """获取包含认证信息的 index URLs."""
        try:
            from airflow.models import Variable

            pypi_username = Variable.get("PYPI_SERVER_USERNAME", default_var=None)
            pypi_password = Variable.get("PYPI_SERVER_PASSWORD", default_var=None)

            if pypi_username and pypi_password:
                return [f"https://{pypi_username}:{pypi_password}@pypiserver.shawndeng.cc/simple/"]
            else:
                return ["https://pypiserver.shawndeng.cc/simple/"]
        except Exception:
            return ["https://pypiserver.shawndeng.cc/simple/"]

    @task.virtualenv(
        task_id="account_snapshot_task",
        requirements=[
            "homelab-database",
            "ibkr-quant>=0.7.0",
        ],
        system_site_packages=False,
        index_urls=get_index_urls(),
    )
    def account_snapshot_task():
        """在虚拟环境中运行账户快照数据采集."""
        from airflow.models import Variable
        from scripts import account_snapshot

        # 配置参数 - 从Airflow变量获取
        database_url = Variable.get("DATABASE_URL", default_var="postgresql://user:password@localhost:5432/database")
        ibkr_host = Variable.get("IBKR_HOST", default_var="192.168.31.53")
        port = int(Variable.get("IBKR_PORT", default_var="4002"))
        client_id = int(Variable.get("IBKR_CLIENT_ID", default_var="1"))

        result = account_snapshot(database_url=database_url, ibkr_host=ibkr_host, port=port, client_id=client_id)

        return result

    # 执行任务
    account_snapshot_task()


# 实例化DAG
ibkr_account_snapshot_dag()
