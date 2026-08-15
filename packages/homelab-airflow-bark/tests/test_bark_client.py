"""Tests for Bark notifications."""

from unittest.mock import Mock

import homelab_airflow_bark
from homelab_airflow_bark.bark_client import BarkClient
from homelab_airflow_bark.schemas import BarkPushMessage
from pydantic import ValidationError


def test_build_push_url():
    """Build the Bark push endpoint URL."""
    assert BarkClient.build_push_url("http://bark.example.com/") == "http://bark.example.com/push"


def test_package_exports():
    """Verify package-level exports."""
    assert homelab_airflow_bark.BarkClient is BarkClient
    assert homelab_airflow_bark.BarkPushMessage is BarkPushMessage


def test_bark_message_validates_and_serializes():
    """Validate and serialize a Bark message payload."""
    message = BarkPushMessage(
        base_url="http://bark.example.com",
        device_key="device-key",
        title="Done",
        body="Upload finished",
        subtitle="bilibili",
        url="https://example.com/video",
        auto_copy=True,
    )

    payload = message.to_payload()

    assert payload["device_key"] == "device-key"
    assert payload["autoCopy"] == 1
    assert payload["title"] == "Done"
    assert "auto_copy" not in payload
    assert "is_archive" not in payload


def test_bark_message_rejects_invalid_level():
    """Reject unsupported Bark interruption levels."""
    try:
        BarkPushMessage(
            base_url="http://bark.example.com",
            device_key="device-key",
            title="Done",
            body="Upload finished",
            level="urgent",
        )
    except ValidationError as exc:
        assert "level" in str(exc)
    else:
        raise AssertionError("Expected ValidationError for invalid Bark level")


def test_send_posts_json_payload(mocker):
    """Send the Bark payload with the expected JSON body."""
    post = mocker.patch(
        "homelab_airflow_bark.bark_client.requests.post",
        return_value=Mock(
            url="http://bark.example.com/push",
            status_code=200,
            ok=True,
            json=Mock(return_value={"code": 200}),
            text='{"code": 200}',
            raise_for_status=Mock(return_value=None),
        ),
    )

    client = BarkClient()
    message = BarkPushMessage(
        base_url="http://bark.example.com",
        device_key="device-key",
        title="Done",
        body="Upload finished",
        subtitle="bilibili",
        url="https://example.com/video",
        auto_copy=True,
    )
    result = client.send(message)

    post.assert_called_once()
    assert post.call_args.kwargs["json"] == {
        "device_key": "device-key",
        "title": "Done",
        "body": "Upload finished",
        "level": "active",
        "subtitle": "bilibili",
        "url": "https://example.com/video",
        "autoCopy": 1,
    }
    assert result.status_code == 200
    assert result.ok is True
