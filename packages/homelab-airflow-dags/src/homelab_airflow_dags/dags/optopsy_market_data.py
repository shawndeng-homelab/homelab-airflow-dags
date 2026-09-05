"""Incrementally load Optopsy options and stock data into PostgreSQL."""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import date
from datetime import timedelta
from typing import Literal

import pandas as pd
import pendulum
from airflow.decorators import dag
from airflow.decorators import task
from airflow.hooks.base import BaseHook
from airflow.models import Variable

from homelab_airflow_dags.common_tasks.exchange_calendars import get_xnys_calendar


DATABASE_CONNECTION_ID = "optopsy_postgres"
EODHD_CONNECTION_ID = "eodhd_default"
SYMBOLS_VARIABLE = "optopsy_market_symbols"
NEW_YORK_TIMEZONE = "America/New_York"
DatasetType = Literal["options", "stocks"]
_DOWNLOAD_FAILURE_MARKERS = (
    "No data provider is configured",
    "No data returned for ",
    "Error fetching ",
)


def scheduled_session_date(context: dict) -> date:
    """Return the New York session date represented by an Airflow run."""
    interval_end = context.get("data_interval_end") or context["logical_date"]
    return interval_end.in_timezone(NEW_YORK_TIMEZONE).date()


def normalize_optopsy_symbols(symbols: object) -> list[str]:
    """Validate, normalize, and deduplicate configured US ticker symbols."""
    if not isinstance(symbols, list) or not symbols:
        raise ValueError(f"Airflow Variable {SYMBOLS_VARIABLE!r} must be a non-empty JSON list")

    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError(f"Airflow Variable {SYMBOLS_VARIABLE!r} must contain non-empty strings")
        value = symbol.strip().upper()
        if value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized


def build_download_command(symbol: str, dataset_type: DatasetType) -> list[str]:
    """Build the Optopsy CLI command without exposing credentials."""
    executable = shutil.which("optopsy-data")
    if executable is None:
        raise FileNotFoundError("optopsy-data is not installed or is not on PATH")
    command = [executable, "download", symbol]
    if dataset_type == "stocks":
        command.append("--stocks")
    command.append("-v")
    return command


def get_database_url() -> str:
    """Return the supported PostgreSQL URI configured in Airflow."""
    database_url = BaseHook.get_connection(DATABASE_CONNECTION_ID).get_uri()
    if not database_url.startswith(("postgres://", "postgresql://")):
        raise ValueError(f"Airflow Connection {DATABASE_CONNECTION_ID!r} must be a PostgreSQL connection")
    return database_url


def get_eodhd_api_key() -> str:
    """Read the EODHD API key from the password field of its Connection."""
    api_key = BaseHook.get_connection(EODHD_CONNECTION_ID).password
    if not api_key:
        raise ValueError(f"Airflow Connection {EODHD_CONNECTION_ID!r} must have an API key in password")
    return api_key


def run_optopsy_cli(command: list[str], environment: dict[str, str]) -> None:
    """Stream Optopsy output and fail on process or known partial-download errors."""
    process = subprocess.Popen(
        command,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    detected_errors: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="")
        if any(marker in line for marker in _DOWNLOAD_FAILURE_MARKERS) or "— skipping" in line:
            detected_errors.append(line.strip())

    return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)
    if detected_errors:
        details = "; ".join(detected_errors[:3])
        raise RuntimeError(f"Optopsy reported download errors: {details}")


@dag(
    dag_id="optopsy_market_data",
    description="Download Optopsy options and stock history into PostgreSQL after US market close.",
    schedule="0 19 * * 1-5",
    start_date=pendulum.datetime(2026, 9, 7, tz=NEW_YORK_TIMEZONE),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "shawndeng",
        "retries": 2,
        "retry_delay": timedelta(minutes=10),
        "execution_timeout": timedelta(hours=6),
    },
    tags=["market-data", "optopsy", "eodhd", "postgresql"],
)
def optopsy_market_data_dag():
    """Download configured symbols after US market close on trading days."""

    @task.short_circuit(task_id="is_xnys_trading_day")
    def is_xnys_trading_day() -> bool:
        from airflow.operators.python import get_current_context

        session_date = scheduled_session_date(get_current_context())
        is_trading_day = get_xnys_calendar().is_session(pd.Timestamp(session_date))
        if not is_trading_day:
            print(f"XNYS is closed on {session_date}; skipping Optopsy downloads.")
        return is_trading_day

    @task(task_id="resolve_symbols")
    def resolve_symbols() -> list[str]:
        return normalize_optopsy_symbols(Variable.get(SYMBOLS_VARIABLE, deserialize_json=True))

    @task(task_id="initialize_database")
    def initialize_database() -> None:
        """Create Optopsy tables before mapped tasks can initialize concurrently."""
        executable = shutil.which("optopsy-data")
        if executable is None:
            raise FileNotFoundError("optopsy-data is not installed or is not on PATH")
        environment = os.environ.copy()
        environment["DATABASE_URL"] = get_database_url()
        subprocess.run([executable, "cache", "size"], check=True, env=environment)

    def download_market_data(symbol: str, dataset_type: DatasetType) -> None:
        command = build_download_command(symbol, dataset_type)
        environment = os.environ.copy()
        environment["DATABASE_URL"] = get_database_url()
        if dataset_type == "options":
            environment["EODHD_API_KEY"] = get_eodhd_api_key()

        print(f"Starting Optopsy {dataset_type} download for {symbol}: {' '.join(command)}")
        run_optopsy_cli(command, environment)

    @task(task_id="download_options", max_active_tis_per_dag=1)
    def download_options(symbol: str) -> None:
        """Download options serially per EODHD key."""
        download_market_data(symbol, "options")

    @task(task_id="download_stocks", max_active_tis_per_dag=1)
    def download_stocks(symbol: str) -> None:
        """Download stock history with independent bounded concurrency."""
        download_market_data(symbol, "stocks")

    trading_day = is_xnys_trading_day()
    symbols = resolve_symbols()
    database = initialize_database()
    options = download_options.expand(symbol=symbols)
    stocks = download_stocks.expand(symbol=symbols)
    trading_day >> symbols
    trading_day >> database
    database >> [options, stocks]


optopsy_market_data = optopsy_market_data_dag()
