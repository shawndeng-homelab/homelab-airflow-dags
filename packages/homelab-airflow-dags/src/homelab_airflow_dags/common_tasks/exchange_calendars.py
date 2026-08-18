from zoneinfo import ZoneInfo

import exchange_calendars as xcals
import pandas as pd
from airflow.decorators import task
from loguru import logger
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class MarketStatus(BaseModel):
    """Market status data structure for inter-task communication with automatic XCom serialization.

    This Pydantic v2 model encapsulates XNYS market state information and automatically
    serializes to dict for transmission between Airflow tasks via XCom.

    Attributes:
        is_open: Whether the market is currently open for trading.
        is_trading_day: Whether today is a trading session (excludes weekends, holidays).
        current_time: Current UTC timestamp in ISO 8601 format.
        open_time: Market opening time in ISO 8601 format (None if non-trading day).
        close_time: Market closing time in ISO 8601 format (None if non-trading day).
        next_trading_day: ISO date string of the next trading day (None if today is trading day).

    Example:
        >>> from homelab_airflow_dags.common_tasks.exchange_calendars import check_market_status
        >>> status_dict = check_market_status()  # Returns dict from model_dump()
        >>> status = MarketStatus(**status_dict)
        >>> if status.is_trading_day and status.is_open:
        ...     print(f"Market open until {status.close_time}")
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "is_open": True,
                "is_trading_day": True,
                "current_time": "2024-01-02T14:30:00+00:00",
                "open_time": "2024-01-02T14:30:00+00:00",
                "close_time": "2024-01-02T21:00:00+00:00",
            }
        },
        frozen=False,
        validate_assignment=True,
    )

    is_open: bool = Field(description="Whether market is currently open")
    is_trading_day: bool = Field(description="Whether today is a trading day")
    current_time: str = Field(description="Current timestamp in ISO format")
    open_time: str | None = Field(None, description="Market open time")
    close_time: str | None = Field(None, description="Market close time")
    next_trading_day: str | None = Field(None, description="Next trading day")


def get_xnys_calendar():
    """Get XNYS (New York Stock Exchange) calendar instance.

    Returns a cached exchange_calendars object for the NYSE, which provides
    trading sessions, market hours, and holiday calendars.

    Returns:
        exchange_calendars.ExchangeCalendar: XNYS calendar object with trading dates
            and market hours.

    Example:
        >>> calendar = get_xnys_calendar()
        >>> import pandas as pd
        >>> today = pd.Timestamp.now().date()
        >>> is_trading = calendar.is_session(pd.Timestamp(today))
        >>> print(f"Today is trading day: {is_trading}")
    """
    return xcals.get_calendar("XNYS")


@task.sensor(poke_interval=60, timeout=3600, mode="poke")
def wait_for_market_open(check_current_time: bool = True, check_trading_day: bool = True) -> bool:
    """Sensor that blocks until XNYS market is open.

    This sensor performs periodic checks to determine if the market is open.
    It can optionally validate that today is a trading day and/or that the
    current time is within market hours.

    Args:
        check_current_time: If True, also checks if current time is within market hours.
            If False, only validates that today is a trading day. Defaults to True.
        check_trading_day: If True, validates that today is a trading session.
            If False, skips trading day validation. Defaults to True.

    Returns:
        bool: True if market open (or conditions met), False to retry poke.

    Raises:
        AirflowTaskTimeout: If market doesn't open within 3600 seconds (1 hour).

    Example:
        >>> from airflow.decorators import dag, task
        >>> from homelab_airflow_dags.common_tasks.exchange_calendars import wait_for_market_open
        >>> @dag(schedule="30 14 * * 1-5")  # 14:30 UTC (09:30 EST)
        ... def example_dag():
        ...     # Wait for market to open, considering both day and time
        ...     market_open = wait_for_market_open(
        ...         check_current_time=True,
        ...         check_trading_day=True
        ...     )
        ...     @task
        ...     def collect_snapshot():
        ...         return "snapshot data"
        ...     market_open >> collect_snapshot()
        >>> example_dag()
    """
    calendar = get_xnys_calendar()
    now = pd.Timestamp.now(tz=ZoneInfo("UTC"))
    session_label = pd.Timestamp(now.date())  # Normalize to midnight, timezone naive
    is_session = calendar.is_session(session_label)

    match (check_trading_day and not is_session, check_current_time):
        case (True, _):
            # Get next session by looking ahead from current date
            next_day = calendar.sessions[calendar.sessions > session_label][0]
            logger.info(f"Not a trading day. Next session: {next_day.date()}")
            return False
        case (False, False):
            logger.info("Today is a trading day")
            return True
        case _:
            is_open = calendar.is_open_on_minute(now)
            status = "open" if is_open else "closed"
            schedule = calendar.schedule.loc[session_label.date()] if is_session and not is_open else None
            msg = f"Market is {status}" + (f" - opens at {schedule['open']}" if schedule is not None else f" - {now}")
            logger.info(msg)
            return is_open


@task.sensor(poke_interval=300, timeout=7200, mode="poke")
def wait_for_trading_day() -> bool:
    """Sensor that blocks until today is a trading day.

    Performs periodic checks to determine if the current date is a valid XNYS
    trading session. This is useful for scheduling tasks that should only run
    on trading days, ignoring weekends and market holidays automatically.

    Returns:
        bool: True if today is a trading day, False to retry poke.

    Raises:
        AirflowTaskTimeout: If today becomes a trading day within 7200 seconds (2 hours).

    Example:
        >>> from airflow.decorators import dag, task
        >>> from homelab_airflow_dags.common_tasks.exchange_calendars import wait_for_trading_day
        >>> @dag(schedule="0 0 * * *")  # Every day at midnight UTC
        ... def daily_reports():
        ...     # Only proceed if today is a trading day
        ...     check_trading = wait_for_trading_day()
        ...     @task
        ...     def generate_report():
        ...         return "daily trading report"
        ...     check_trading >> generate_report()
        >>> daily_reports()
    """
    calendar = get_xnys_calendar()
    now = pd.Timestamp.now(tz=ZoneInfo("UTC"))
    session_label = pd.Timestamp(now.date())  # Normalize to midnight, timezone naive
    is_trading = calendar.is_session(session_label)

    next_or_current = (
        session_label.date() if is_trading else calendar.sessions[calendar.sessions > session_label][0].date()
    )
    status = "is" if is_trading else "not"
    logger.info(f"Today {status} a trading day. Next/current session: {next_or_current}")

    return is_trading


@task
def check_market_status() -> dict:
    """Non-blocking task that returns current market status immediately.

    Queries the current market state and returns a MarketStatus model serialized
    as a dictionary. This task completes immediately without waiting and is useful
    for:
    - Checking status conditionally without blocking the DAG
    - Logging current market state for debugging
    - Passing market info downstream to dependent tasks

    Returns:
        dict: Serialized MarketStatus containing:
            - is_open (bool): Current market open status
            - is_trading_day (bool): Whether today is a trading session
            - current_time (str): Current UTC time in ISO 8601 format
            - open_time (str|None): Market open time, None if non-trading day
            - close_time (str|None): Market close time, None if non-trading day
            - next_trading_day (str|None): ISO date of next trading day if today is not

    Example:
        >>> from airflow.decorators import dag, task
        >>> from homelab_airflow_dags.common_tasks.exchange_calendars import check_market_status
        >>> @dag(schedule="@hourly")
        ... def monitor_market():
        ...     status = check_market_status()
        ...     @task
        ...     def log_status(market_status: dict):
        ...         if market_status['is_trading_day']:
        ...             if market_status['is_open']:
        ...                 print(f"Market open until {market_status['close_time']}")
        ...             else:
        ...                 print(f"Market hours: {market_status['open_time']} - {market_status['close_time']}")
        ...         else:
        ...             print(f"Not a trading day. Next: {market_status['next_trading_day']}")
        ...     log_status(status)
        >>> monitor_market()
    """
    calendar = get_xnys_calendar()
    now = pd.Timestamp.now(tz=ZoneInfo("UTC"))
    session_label = pd.Timestamp(now.date())  # Normalize to midnight, timezone naive
    is_trading_day = calendar.is_session(session_label)

    status = MarketStatus(
        is_open=calendar.is_open_on_minute(now) if is_trading_day else False,
        is_trading_day=is_trading_day,
        current_time=now.isoformat(),
    )

    match (is_trading_day, status.is_open):
        case (True, True):
            schedule = calendar.schedule.loc[session_label.date()]
            status.open_time = schedule["open"].isoformat()
            status.close_time = schedule["close"].isoformat()
            log_msg = "Market is open"
        case (True, False):
            schedule = calendar.schedule.loc[session_label.date()]
            status.open_time = schedule["open"].isoformat()
            status.close_time = schedule["close"].isoformat()
            log_msg = f"Market closed. Hours: {schedule['open']} - {schedule['close']}"
        case _:
            next_day = calendar.sessions[calendar.sessions > session_label][0]
            status.next_trading_day = next_day.date().isoformat()
            log_msg = f"Market is not trading. Next: {next_day.date()}"

    logger.info(log_msg)
    return status.model_dump()  # Pydantic v2: auto serialize to dict


@task.sensor(poke_interval=60, timeout=1800, mode="poke")
def wait_for_market_close() -> bool:
    """Sensor that blocks until XNYS market is closed.

    Performs periodic checks to wait for market close. This sensor is useful for
    end-of-day operations that should only run after the market closes. It returns
    immediately (True) if today is not a trading day or market is not open.

    Returns:
        bool: True if market is closed (or non-trading day), False to retry poke.

    Raises:
        AirflowTaskTimeout: If market doesn't close within 1800 seconds (30 minutes).

    Example:
        >>> from airflow.decorators import dag, task
        >>> from homelab_airflow_dags.common_tasks.exchange_calendars import wait_for_market_close
        >>> @dag(schedule="0 20 * * 1-5")  # 20:00 UTC (15:00 EST - market close)
        ... def end_of_day_processing():
        ...     market_close = wait_for_market_close()
        ...     @task
        ...     def calculate_daily_stats():
        ...         return "daily statistics"
        ...     market_close >> calculate_daily_stats()
        >>> end_of_day_processing()
    """
    calendar = get_xnys_calendar()
    now = pd.Timestamp.now(tz=ZoneInfo("UTC"))
    session_label = pd.Timestamp(now.date())  # Normalize to midnight, timezone naive
    is_trading = calendar.is_session(session_label)
    is_open = calendar.is_open_on_minute(now) if is_trading else False

    should_wait = is_trading and is_open
    schedule = calendar.schedule.loc[session_label.date()] if is_trading and is_open else None

    status = "open" if should_wait else ("closed" if is_trading else "not trading")
    msg = f"Market {status}" + (f". Closes at {schedule['close']}" if schedule is not None else "")
    logger.info(msg)

    return not should_wait
