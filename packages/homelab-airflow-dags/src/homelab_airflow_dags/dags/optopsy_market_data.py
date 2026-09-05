"""Incrementally load Optopsy options and stock data into PostgreSQL."""

from __future__ import annotations

import os
import shutil
import subprocess
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

        logical_date = get_current_context()["logical_date"].in_timezone(NEW_YORK_TIMEZONE)
        is_trading_day = get_xnys_calendar().is_session(pd.Timestamp(logical_date.date()))
        if not is_trading_day:
            print(f"XNYS is closed on {logical_date.date()}; skipping Optopsy downloads.")
        return is_trading_day

    @task(task_id="resolve_symbols")
    def resolve_symbols() -> list[str]:
        return normalize_optopsy_symbols(Variable.get(SYMBOLS_VARIABLE, deserialize_json=True))

    @task(task_id="build_download_work")
    def build_download_work(symbols: list[str]) -> list[dict[str, str]]:
        return [
            {"symbol": symbol, "dataset_type": dataset_type}
            for symbol in symbols
            for dataset_type in ("options", "stocks")
        ]

    @task(task_id="download_market_data", max_active_tis_per_dag=2)
    def download_market_data(symbol: str, dataset_type: DatasetType) -> None:
        command = build_download_command(symbol, dataset_type)
        environment = os.environ.copy()
        environment["DATABASE_URL"] = get_database_url()
        if dataset_type == "options":
            environment["EODHD_API_KEY"] = get_eodhd_api_key()

        print(f"Starting Optopsy {dataset_type} download for {symbol}: {' '.join(command)}")
        subprocess.run(command, check=True, env=environment)

    trading_day = is_xnys_trading_day()
    symbols = resolve_symbols()
    work = build_download_work(symbols)
    downloads = download_market_data.expand_kwargs(work)
    trading_day >> symbols
    trading_day >> downloads


optopsy_market_data = optopsy_market_data_dag()
