"""Deferrable trigger for asynchronous localization jobs."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

import aiohttp
from airflow.exceptions import AirflowException
from airflow.triggers.base import BaseTrigger
from airflow.triggers.base import TriggerEvent

from homelab_airflow_providers_localization.hooks.localization import LocalizationHook
from homelab_airflow_providers_localization.models import parse_localization_job


class LocalizationJobTrigger(BaseTrigger):
    """Poll a localization job without occupying an Airflow worker slot."""

    def __init__(
        self,
        *,
        job_id: str,
        localization_conn_id: str = LocalizationHook.default_conn_name,
        poll_interval: float = 10.0,
    ) -> None:
        """Initialize a serializable job poller."""
        super().__init__()
        if poll_interval <= 0:
            raise ValueError("poll_interval must be greater than zero")
        self.job_id = job_id
        self.localization_conn_id = localization_conn_id
        self.poll_interval = poll_interval

    def serialize(self) -> tuple[str, dict[str, Any]]:
        """Serialize only stable identifiers; credentials remain in the Connection."""
        return (
            "homelab_airflow_providers_localization.triggers.localization.LocalizationJobTrigger",
            {
                "job_id": self.job_id,
                "localization_conn_id": self.localization_conn_id,
                "poll_interval": self.poll_interval,
            },
        )

    async def run(self) -> AsyncIterator[TriggerEvent]:
        """Yield when the remote job completes or returns a permanent error."""
        try:
            config = LocalizationHook(self.localization_conn_id).get_connection_config()
        except AirflowException as error:
            yield TriggerEvent({"status": "error", "message": str(error)})
            return

        url = f"{config.base_url}/v1/jobs/{quote(self.job_id, safe='')}"
        timeout = aiohttp.ClientTimeout(total=config.timeout)
        async with aiohttp.ClientSession(headers=config.headers, timeout=timeout) as session:
            while True:
                try:
                    async with session.get(url, ssl=config.verify_tls) as response:
                        if 400 <= response.status < 500:
                            yield TriggerEvent(
                                {"status": "error", "message": f"Job polling failed with HTTP {response.status}"}
                            )
                            return
                        if response.status >= 500:
                            self.log.warning("Localization polling returned HTTP %s; retrying", response.status)
                        else:
                            job = parse_localization_job(await response.json(content_type=None))
                            if job.is_terminal:
                                yield TriggerEvent({"status": "success", "job": job.as_dict()})
                                return
                except (TimeoutError, aiohttp.ClientError) as error:
                    self.log.warning("Localization polling failed transiently: %s", error.__class__.__name__)
                except (AirflowException, ValueError) as error:
                    yield TriggerEvent({"status": "error", "message": str(error)})
                    return
                await asyncio.sleep(self.poll_interval)
