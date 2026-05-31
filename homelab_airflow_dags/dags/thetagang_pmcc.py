"""ThetaGang PMCC Strategy - Airflow DAG.

Executes the ThetaGang PMCC strategy every trading day after market open.
Flow: market sensor -> dry-run -> live run -> query results.

The DAG uses KubernetesPodOperator to launch thetagang as an isolated Pod,
mounting ConfigMap for configuration and PVC for persistent SQLite database.
"""

from datetime import timedelta

import pendulum
from airflow.decorators import dag
from airflow.decorators import task
from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from kubernetes.client import models as k8s
from loguru import logger

from homelab_airflow_dags.common_tasks.exchange_calendars import wait_for_market_open


# ─── K8s configuration ───

NAMESPACE = "default"
IMAGE = "brndnmtthws/thetagang:main"
CONFIG_PATH = "/etc/thetagang/thetagang.toml"
DATA_PATH = "/var/lib/thetagang"
DB_PATH = f"{DATA_PATH}/thetagang.db"


default_args = {
    "owner": "shawndeng",
    "depends_on_past": False,
    "start_date": pendulum.datetime(2025, 11, 6, tz="UTC"),
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=10),
    "execution_timeout": timedelta(minutes=30),
}


def _thetagang_pod_config(dry_run: bool) -> dict:
    """Build KubernetesPodOperator kwargs for thetagang Pod."""
    cmds = ["thetagang", "--config", CONFIG_PATH, "--without-ibc"]
    if dry_run:
        cmds.append("--dry-run")

    volume_mounts = [
        k8s.V1VolumeMount(name="config", mount_path="/etc/thetagang", read_only=True),
        k8s.V1VolumeMount(name="data", mount_path=DATA_PATH),
    ]

    volumes = [
        k8s.V1Volume(name="config", config_map=k8s.V1ConfigMapVolumeSource(name="thetagang-config")),
        k8s.V1Volume(
            name="data",
            persistent_volume_claim=k8s.V1PersistentVolumeClaimVolumeSource(claim_name="thetagang-data"),
        ),
    ]

    return {
        "image": IMAGE,
        "cmds": cmds,
        "name": f"thetagang-{'dryrun' if dry_run else 'live'}",
        "namespace": NAMESPACE,
        "is_delete_operator_pod": True,
        "get_logs": True,
        "log_events_on_failure": True,
        "volume_mounts": volume_mounts,
        "volumes": volumes,
    }


def _query_run(conn, run_id: int) -> dict:
    """Query all data for a single thetagang run from SQLite."""
    run = conn.execute("SELECT id, started_at, dry_run FROM runs WHERE id = ?", (run_id,)).fetchone()

    intents = conn.execute(
        """SELECT symbol, action, quantity, limit_price, sec_type, dry_run, created_at
           FROM order_intents WHERE run_id = ? ORDER BY created_at""",
        (run_id,),
    ).fetchall()

    positions = conn.execute(
        """SELECT symbol, position, market_value, unrealized_pnl,
                  strike, right, expiry, sec_type
           FROM position_snapshots WHERE run_id = ? ORDER BY symbol, sec_type""",
        (run_id,),
    ).fetchall()

    executions = conn.execute(
        """SELECT symbol, side, shares, price, execution_time
           FROM executions WHERE run_id = ? ORDER BY execution_time""",
        (run_id,),
    ).fetchall()

    return {
        "run": dict(run) if run else None,
        "intents": [dict(r) for r in intents],
        "positions": [dict(r) for r in positions],
        "executions": [dict(r) for r in executions],
    }


def _log_run_results(results: dict) -> None:
    """Log thetagang run results via loguru."""
    run = results["run"]
    if not run:
        logger.warning("No runs found in database")
        return

    logger.info(f"Run #{run['id']} at {run['started_at']} (dry_run={run['dry_run']})")

    intents = results["intents"]
    logger.info(f"Order Intents: {len(intents)} entries")
    for i in intents:
        logger.info(
            f"  {i['created_at']} | {i['symbol']} {i['action']} "
            f"{i['quantity']}x @ ${i['limit_price']} ({i['sec_type']}) [dry_run={i['dry_run']}]"
        )

    positions = results["positions"]
    logger.info(f"Positions: {len(positions)} entries")
    for p in positions:
        detail = ""
        if p["strike"]:
            detail = f" strike={p['strike']} {p['right']} exp={p['expiry']}"
        logger.info(
            f"  {p['symbol']} ({p['sec_type']}) pos={p['position']} "
            f"val=${p['market_value']:.2f} pnl=${p['unrealized_pnl']:.2f}{detail}"
        )

    executions = results["executions"]
    if executions:
        logger.info(f"Executions: {len(executions)} entries")
        for e in executions:
            logger.info(f"  {e['execution_time']} | {e['symbol']} {e['side']} {e['shares']}x @ ${e['price']}")


@dag(
    dag_id="thetagang_pmcc",
    default_args=default_args,
    description="ThetaGang PMCC Strategy - Trading hours only (auto handles holidays & DST)",
    schedule="35 13 * * 1-5",  # 13:35 UTC = 09:35 ET (EST), auto adjusted by market sensor
    catchup=False,
    max_active_runs=1,  # Prevent concurrent SQLite writes
    tags=["thetagang", "trading", "pmcc"],
)
def thetagang_pmcc_dag():
    """ThetaGang PMCC strategy execution during market hours.

    Flow:
        1. wait_for_market_open - Sensor: skip holidays, wait for market open
        2. dry_run - KubernetesPodOperator: dry-run only, record order intents
        3. live_run - KubernetesPodOperator: actual paper trading execution
        4. query_results - Read SQLite and log results
    """
    market_check = wait_for_market_open(check_current_time=True, check_trading_day=True)

    dry_run = KubernetesPodOperator(
        task_id="dry_run",
        **_thetagang_pod_config(dry_run=True),
    )

    live_run = KubernetesPodOperator(
        task_id="live_run",
        **_thetagang_pod_config(dry_run=False),
    )

    @task
    def query_results():
        """Read latest run results from thetagang SQLite database."""
        import sqlite3

        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row

        try:
            run = conn.execute("SELECT id FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()

            if not run:
                logger.warning("No runs found in database")
                return

            results = _query_run(conn, run["id"])
            _log_run_results(results)
        finally:
            conn.close()

    # Workflow: market open -> dry-run -> live -> results
    market_check >> dry_run >> live_run >> query_results()


# Instantiate DAG
thetagang_pmcc_dag()
