from datetime import timedelta

import pendulum
from airflow.decorators import dag
from airflow.decorators import task

from homelab_airflow_dags.common_tasks.exchange_calendars import wait_for_market_open


default_args = {
    "owner": "shawndeng",
    "depends_on_past": False,
    "start_date": pendulum.datetime(2025, 11, 6, tz="UTC"),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}


@dag(
    dag_id="ibkr_account_snapshot",
    default_args=default_args,
    description="IBKR Account Snapshot - Trading hours only (auto handles holidays & DST)",
    schedule="30 14-20 * * 1-5",  # Every hour during US market hours (UTC 14:30-20:30)
    catchup=False,
    tags=["ibkr", "snapshot", "data-collection", "trading-hours"],
)
def ibkr_account_snapshot_dag():
    """IBKR account snapshot data collection during market hours.

    Features:
    - Auto skips holidays (exchange_calendars handles US market calendar)
    - Auto handles DST changes (exchange_calendars uses market timezone)
    - Only executes when market is open
    - Collects hourly snapshots during trading hours
    """
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

    database_url = config.get("database")
    ibkr_args = config.get("ibkr", [])

    # Sensor: ensures market is open before executing
    # - Auto skips non-trading days (weekends, holidays)
    # - Auto handles DST transitions
    # - Waits if triggered slightly before market open
    market_check = wait_for_market_open(check_current_time=True, check_trading_day=True)

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

    # Workflow: wait for market open -> collect snapshot
    snapshot = account_snapshot_task(database_url, ibkr_args)
    market_check >> snapshot


# Instantiate DAG
ibkr_account_snapshot_dag()
