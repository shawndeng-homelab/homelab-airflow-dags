"""Tests for Bark schemas and HTTP transport."""

from unittest.mock import Mock

import homelab_airflow_bark
from homelab_airflow_bark.bark_client import BarkClient
from homelab_airflow_bark.schemas import BarkPushMessage
from pydantic import ValidationError


def test_build_push_url() -> None:
    """Build the Bark push endpoint URL."""
    assert BarkClient.build_push_url("http://bark.example.com/") == "http://bark.example.com/push"


def test_package_exports() -> None:
    """Keep the existing package-level client and schema exports."""
    assert homelab_airflow_bark.BarkClient is BarkClient
    assert homelab_airflow_bark.BarkPushMessage is BarkPushMessage


def test_bark_message_contains_no_connection_credentials() -> None:
    """Serialize only notification data, never transport credentials."""
    message = BarkPushMessage(
        title="Done",
        body="Upload finished",
        subtitle="bilibili",
        url="https://example.com/video",
        auto_copy=True,
    )

    payload = message.to_payload()

    assert payload["autoCopy"] == 1
    assert payload["title"] == "Done"
    assert "base_url" not in payload
    assert "device_key" not in payload


def test_bark_message_rejects_invalid_level() -> None:
    """Reject unsupported Bark interruption levels."""
    try:
        BarkPushMessage(title="Done", body="Upload finished", level="urgent")
    except ValidationError as error:
        assert "level" in str(error)
    else:
        raise AssertionError("Expected ValidationError for invalid Bark level")


def test_send_posts_connection_device_key(mocker) -> None:
    """Combine the client credential with the validated message at send time."""
    post = mocker.patch(
        "homelab_airflow_bark.bark_client.requests.post",
        return_value=Mock(
            url="http://bark.example.com/push",
            status_code=200,
            ok=True,
            json=Mock(return_value={"code": 200}),
            text="success",
            raise_for_status=Mock(return_value=None),
        ),
    )
    client = BarkClient(base_url="http://bark.example.com", device_key="device-key")
    result = client.send(BarkPushMessage(title="Done", body="Upload finished", auto_copy=True))

    assert post.call_args.kwargs["json"] == {
        "device_key": "device-key",
        "title": "Done",
        "body": "Upload finished",
        "level": "active",
        "autoCopy": 1,
    }
    assert post.call_args.kwargs["verify"] is True
    assert result.ok is True
