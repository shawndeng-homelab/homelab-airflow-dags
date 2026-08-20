"""Airflow Connection-backed Bark hook."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook

from homelab_airflow_bark.bark_client import BarkClient
from homelab_airflow_bark.bark_client import BarkResponse
from homelab_airflow_bark.schemas import BarkPushMessage


class BarkHook(BaseHook):
    """Send Bark messages using credentials stored in an Airflow Connection."""

    conn_name_attr = "bark_conn_id"
    default_conn_name = "bark_default"
    conn_type = "bark"
    hook_name = "Bark"

    def __init__(self, bark_conn_id: str = default_conn_name, *, timeout: float | None = None) -> None:
        """Initialize the hook with an optional request-timeout override."""
        super().__init__()
        self.bark_conn_id = bark_conn_id
        self.timeout = timeout

    @classmethod
    def get_ui_field_behaviour(cls) -> dict[str, Any]:
        """Describe how the Bark connection maps to standard fields."""
        return {
            "hidden_fields": ["schema", "login", "port"],
            "relabeling": {"host": "Bark server URL", "password": "Device key"},
            "placeholders": {
                "host": "https://api.day.app",
                "password": "Bark device key",
                "extra": "JSON object with timeout and verify_tls",
            },
        }

    def get_conn(self) -> BarkClient:
        """Create a configured Bark client from the Airflow Connection."""
        connection = self.get_connection(self.bark_conn_id)
        if not connection.host:
            raise AirflowException(f"Connection {self.bark_conn_id!r} must define the Bark server URL in Host")
        parsed_url = urlparse(connection.host)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            raise AirflowException("Bark server URL must be an absolute HTTP or HTTPS URL")
        if not connection.password:
            raise AirflowException(f"Connection {self.bark_conn_id!r} must define the device key in Password")

        extra = connection.extra_dejson
        timeout = self.timeout if self.timeout is not None else float(extra.get("timeout", 10))
        if timeout <= 0:
            raise AirflowException("Bark request timeout must be greater than zero")
        verify_tls = extra.get("verify_tls", True)
        if not isinstance(verify_tls, bool):
            raise AirflowException("Bark verify_tls must be a boolean")
        return BarkClient(
            base_url=connection.host,
            device_key=connection.password,
            timeout=timeout,
            verify_tls=verify_tls,
        )

    def send(self, message: BarkPushMessage | dict[str, Any]) -> BarkResponse:
        """Validate and send a Bark notification."""
        return self.get_conn().send(BarkPushMessage.model_validate(message))

    def test_connection(self) -> tuple[bool, str]:
        """Validate connection fields without sending a notification."""
        try:
            self.get_conn()
        except (AirflowException, ValueError) as error:
            return False, str(error)
        return True, "Bark connection configuration is valid; no notification was sent"
