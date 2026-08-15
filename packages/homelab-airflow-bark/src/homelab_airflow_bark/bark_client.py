"""Bark HTTP client."""

from typing import Any

import requests
from pydantic import BaseModel
from pydantic import ConfigDict

from homelab_airflow_bark.schemas import BarkPushMessage


class BarkResponse(BaseModel):
    """Normalized Bark response.

    Attributes:
        url: Final request URL returned by the HTTP client.
        status_code: HTTP status code returned by Bark.
        ok: Whether the request succeeded.
        payload: Parsed JSON response or raw text fallback.
    """

    model_config = ConfigDict(extra="forbid")

    url: str
    status_code: int
    ok: bool
    payload: dict[str, Any]


class BarkClient:
    """Send push notifications to Bark.

    Args:
        timeout: Request timeout in seconds.
    """

    def __init__(self, timeout: int = 10) -> None:
        """Initialize the Bark client.

        Args:
            timeout: Request timeout in seconds.
        """
        self.timeout = timeout

    @staticmethod
    def build_push_url(base_url: str) -> str:
        """Build the Bark JSON push URL.

        Args:
            base_url: Bark server base URL.

        Returns:
            The absolute `/push` endpoint URL.
        """
        return f"{base_url.rstrip('/')}/push"

    def send(self, message: BarkPushMessage) -> BarkResponse:
        """Send a Bark push notification.

        Args:
            message: Validated Bark push payload.

        Returns:
            A normalized Bark response object.
        """
        response = requests.post(
            self.build_push_url(str(message.base_url)),
            json=message.to_payload(),
            timeout=self.timeout,
        )
        response.raise_for_status()

        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {"raw": response.text}

        return BarkResponse(
            url=response.url,
            status_code=response.status_code,
            ok=response.ok,
            payload=response_payload,
        )
