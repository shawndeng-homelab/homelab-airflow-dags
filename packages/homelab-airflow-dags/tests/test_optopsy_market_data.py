"""Tests for the Optopsy market-data DAG helpers."""

from __future__ import annotations

import subprocess
from unittest.mock import Mock

import pendulum
import pytest
from homelab_airflow_dags.dags.optopsy_market_data import DATABASE_CONNECTION_ID
from homelab_airflow_dags.dags.optopsy_market_data import EODHD_CONNECTION_ID
from homelab_airflow_dags.dags.optopsy_market_data import build_download_command
from homelab_airflow_dags.dags.optopsy_market_data import get_database_url
from homelab_airflow_dags.dags.optopsy_market_data import get_eodhd_api_key
from homelab_airflow_dags.dags.optopsy_market_data import normalize_optopsy_symbols
from homelab_airflow_dags.dags.optopsy_market_data import optopsy_market_data
from homelab_airflow_dags.dags.optopsy_market_data import run_optopsy_cli
from homelab_airflow_dags.dags.optopsy_market_data import scheduled_session_date


def test_normalize_optopsy_symbols_trims_uppercases_and_deduplicates():
    """Configured symbols are normalized before dynamic mapping."""
    assert normalize_optopsy_symbols([" spy ", "AAPL", "SPY", "tsla"]) == ["SPY", "AAPL", "TSLA"]


@pytest.mark.parametrize("value", [None, [], "SPY", [""], [None]])
def test_normalize_optopsy_symbols_rejects_invalid_values(value):
    """The required Airflow Variable must be a non-empty symbol list."""
    with pytest.raises(ValueError, match="optopsy_market_symbols"):
        normalize_optopsy_symbols(value)


def test_build_download_command_uses_verbose_options_cli(mocker):
    """Options CLI invocations always include verbose logging."""
    mocker.patch(
        "homelab_airflow_dags.dags.optopsy_market_data.shutil.which", return_value="/usr/local/bin/optopsy-data"
    )

    assert build_download_command("SPY", "options") == ["/usr/local/bin/optopsy-data", "download", "SPY", "-v"]


def test_build_download_command_uses_verbose_stock_cli(mocker):
    """Stock CLI invocations select stock history and verbose logging."""
    mocker.patch(
        "homelab_airflow_dags.dags.optopsy_market_data.shutil.which", return_value="/usr/local/bin/optopsy-data"
    )

    assert build_download_command("SPY", "stocks") == [
        "/usr/local/bin/optopsy-data",
        "download",
        "SPY",
        "--stocks",
        "-v",
    ]


def test_build_download_command_requires_cli(mocker):
    """A missing CLI fails before any credentials are read."""
    mocker.patch("homelab_airflow_dags.dags.optopsy_market_data.shutil.which", return_value=None)

    with pytest.raises(FileNotFoundError, match="optopsy-data"):
        build_download_command("SPY", "options")


def test_get_database_url_reads_postgres_connection(mocker):
    """The target database is loaded from its dedicated Connection."""
    connection = Mock()
    connection.get_uri.return_value = "postgresql://optopsy:secret@postgres/optopsy"
    get_connection = mocker.patch(
        "homelab_airflow_dags.dags.optopsy_market_data.BaseHook.get_connection", return_value=connection
    )

    assert get_database_url() == "postgresql://optopsy:secret@postgres/optopsy"
    get_connection.assert_called_once_with(DATABASE_CONNECTION_ID)


def test_get_database_url_rejects_non_postgres_connection(mocker):
    """Only a PostgreSQL URI can activate Optopsy's database backend."""
    connection = Mock()
    connection.get_uri.return_value = "mysql://optopsy:secret@database/optopsy"
    mocker.patch("homelab_airflow_dags.dags.optopsy_market_data.BaseHook.get_connection", return_value=connection)

    with pytest.raises(ValueError, match=DATABASE_CONNECTION_ID):
        get_database_url()


def test_get_eodhd_api_key_reads_connection_password(mocker):
    """The EODHD credential is read from the Connection password."""
    connection = Mock(password="api-key")
    get_connection = mocker.patch(
        "homelab_airflow_dags.dags.optopsy_market_data.BaseHook.get_connection", return_value=connection
    )

    assert get_eodhd_api_key() == "api-key"
    get_connection.assert_called_once_with(EODHD_CONNECTION_ID)


def test_get_eodhd_api_key_requires_password(mocker):
    """Missing EODHD credentials fail before the CLI is launched."""
    connection = Mock(password=None)
    mocker.patch("homelab_airflow_dags.dags.optopsy_market_data.BaseHook.get_connection", return_value=connection)

    with pytest.raises(ValueError, match=EODHD_CONNECTION_ID):
        get_eodhd_api_key()


def test_scheduled_session_date_uses_interval_end_after_holiday():
    """The first post-holiday run evaluates its actual session date."""
    context = {
        "logical_date": pendulum.datetime(2026, 9, 4, 23, tz="UTC"),
        "data_interval_end": pendulum.datetime(2026, 9, 8, 23, tz="UTC"),
    }

    assert scheduled_session_date(context).isoformat() == "2026-09-08"


def test_run_optopsy_cli_raises_on_partial_download_error(mocker, capsys):
    """A CLI zero exit code cannot hide an Optopsy skipped window."""
    process = Mock()
    process.stdout = iter(["12:00 Error 2026-09-01–2026-09-30: timeout — skipping\n"])
    process.wait.return_value = 0
    mocker.patch("homelab_airflow_dags.dags.optopsy_market_data.subprocess.Popen", return_value=process)

    with pytest.raises(RuntimeError, match="download errors"):
        run_optopsy_cli(["optopsy-data", "download", "SPY", "-v"], {"DATABASE_URL": "postgresql://db"})

    assert "skipping" in capsys.readouterr().out


def test_run_optopsy_cli_raises_on_nonzero_exit(mocker):
    """A genuine CLI process failure is propagated to Airflow."""
    process = Mock()
    process.stdout = iter([])
    process.wait.return_value = 2
    mocker.patch("homelab_airflow_dags.dags.optopsy_market_data.subprocess.Popen", return_value=process)

    with pytest.raises(subprocess.CalledProcessError):
        run_optopsy_cli(["optopsy-data", "download", "SPY", "-v"], {})


def test_dag_runs_after_market_close_with_bounded_download_concurrency():
    """The production DAG preserves its schedule, holiday gate, and rate-limit boundary."""
    assert optopsy_market_data.schedule_interval == "0 19 * * 1-5"
    assert str(optopsy_market_data.timezone) == "America/New_York"
    expected_tasks = {
        "is_xnys_trading_day",
        "resolve_symbols",
        "initialize_database",
        "download_options",
        "download_stocks",
    }
    assert expected_tasks <= set(optopsy_market_data.task_ids)
    assert optopsy_market_data.get_task("download_options").max_active_tis_per_dag == 1
    assert optopsy_market_data.get_task("download_stocks").max_active_tis_per_dag == 1
