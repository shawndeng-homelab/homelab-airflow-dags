"""Tests for the Airflow Connection-backed Bark hook."""

import json

from airflow.models.connection import Connection
from homelab_airflow_bark.hooks import BarkHook


def test_hook_uses_official_bark_server_placeholder() -> None:
    """Guide Airflow users to the Bark API root rather than a keyed URL."""
    behaviour = BarkHook.get_ui_field_behaviour()

    assert behaviour["placeholders"]["host"] == "https://api.day.app"


def test_hook_maps_connection_fields(mocker) -> None:
    """Map Host, Password, and Extra to a Bark client."""
    hook = BarkHook()
    mocker.patch.object(
        hook,
        "get_connection",
        return_value=Connection(
            conn_id="bark_default",
            host="https://bark.internal/",
            password="device-key",
            extra=json.dumps({"timeout": 12, "verify_tls": False}),
        ),
    )

    client = hook.get_conn()

    assert client.base_url == "https://bark.internal/"
    assert client.device_key == "device-key"
    assert client.timeout == 12
    assert client.verify_tls is False


def test_hook_timeout_override_wins(mocker) -> None:
    """Allow an operator or notifier to override the Connection timeout."""
    hook = BarkHook(timeout=3)
    mocker.patch.object(
        hook,
        "get_connection",
        return_value=Connection(
            conn_id="bark_default",
            host="https://bark.internal",
            password="device-key",
            extra=json.dumps({"timeout": 12}),
        ),
    )

    assert hook.get_conn().timeout == 3
