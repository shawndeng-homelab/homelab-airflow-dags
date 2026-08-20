"""Bark HTTP client."""

from typing import Any
from urllib.parse import quote

import requests
from pydantic import BaseModel
from pydantic import ConfigDict

from homelab_airflow_bark.schemas import BarkPushMessage


class BarkResponse(BaseModel):
    """Normalized Bark response."""

    model_config = ConfigDict(extra="forbid")

    url: str
    status_code: int
    ok: bool
    payload: dict[str, Any]


class BarkClient:
    """Send push notifications to one Bark device."""

    def __init__(
        self,
        *,
        base_url: str,
        device_key: str,
        timeout: float = 10,
        verify_tls: bool = True,
    ) -> None:
        """Initialize the client with transport configuration and credentials."""
        self.base_url = base_url
        self.device_key = device_key
        self.timeout = timeout
        self.verify_tls = verify_tls

    @staticmethod
    def build_push_url(base_url: str, device_key: str) -> str:
        """Build the Bark POST endpoint URL with an encoded device key."""
        return f"{base_url.rstrip('/')}/{quote(device_key, safe='')}"

    def send(self, message: BarkPushMessage) -> BarkResponse:
        """Send a validated Bark push notification."""
        push_url = self.build_push_url(self.base_url, self.device_key)
        response = requests.post(
            push_url,
            json=message.to_payload(),
            timeout=self.timeout,
            verify=self.verify_tls,
        )
        response.raise_for_status()

        try:
            response_payload = response.json()
        except ValueError:
            response_payload = {"raw": response.text}

        return BarkResponse(
            url=f"{self.base_url.rstrip('/')}/***",
            status_code=response.status_code,
            ok=response.ok,
            payload=response_payload,
        )
