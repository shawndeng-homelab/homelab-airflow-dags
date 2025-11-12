from datetime import timedelta

import pendulum
from airflow.decorators import dag
from airflow.decorators import task


default_args = {
    "owner": "shawndeng",
    "depends_on_past": False,
    "start_date": pendulum.datetime(2025, 11, 6, tz="Asia/Shanghai"),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="ibkr_account_snapshot",
    default_args=default_args,
    description="IBKR Account Snapshot Data Collection",
    schedule="0 21-23,0-7 * * 1-5",  # 周一到周五晚上9点到次日早上8点,每小时执行
    catchup=False,
    tags=["ibkr", "snapshot", "data-collection"],
)
def ibkr_account_snapshot_dag():
    """IBKR账户快照数据采集DAG."""
    from urllib.parse import urlparse

    from homelab_airflow_dags.config import get_config

    config = get_config("ibkr_account_snapshot")
    pypi_info = config.get("pypi", {})
    host = pypi_info.get("host", "")
    parsed = urlparse(host)
    netloc_and_path = parsed.netloc + parsed.path
    pypi_user = pypi_info.get("user")
    pypi_password = pypi_info.get("password")

    if netloc_and_path and pypi_user and pypi_password:
        index_url = f"https://{pypi_user}:{pypi_password}@{netloc_and_path}"
        index_urls = [index_url]
    else:
        index_urls = None

    # 提前获取配置参数
    database_url = config.get("database")
    ibkr_args = config.get("ibkr", [])

    @task.virtualenv(
        task_id="account_snapshot_task",
        requirements=["ibkr-quant>=0.7.1"],
        system_site_packages=False,
        index_urls=index_urls,
    )
    def account_snapshot_task(database_url, ibkr_args):
        from scripts.ibkr_account_snapshot import account_snapshot  # type: ignore

        results = []
        for account in ibkr_args:
            results.append(account_snapshot(database_url=database_url, **account))
        return results

    account_snapshot_task(database_url, ibkr_args)


# 实例化DAG
ibkr_account_snapshot_dag()
