"""Tests for the read-only YouTube Data API hook."""

import json
from unittest.mock import Mock

import pytest
from airflow.exceptions import AirflowException
from airflow.models.connection import Connection
from homelab_airflow_providers_youtube.hooks import YouTubeConnectionConfig
from homelab_airflow_providers_youtube.hooks import YouTubeHook


def test_connection_maps_api_key_and_network_settings(mocker) -> None:
    """Connection fields map to Data API settings without logging the key."""
    hook = YouTubeHook()
    mocker.patch.object(
        hook,
        "get_connection",
        return_value=Connection(
            conn_id="youtube_default",
            password="secret-key",
            extra=json.dumps(
                {
                    "timeout": 12,
                    "proxy": "http://proxy.internal:8080",
                    "max_retries": 3,
                }
            ),
        ),
    )

    config = hook.get_connection_config()

    assert config.api_key == "secret-key"
    assert config.timeout == 12
    assert config.proxies == {
        "http": "http://proxy.internal:8080",
        "https": "http://proxy.internal:8080",
    }
    assert config.max_retries == 3


def test_get_channel_returns_shared_contract(mocker) -> None:
    """Channel discovery extracts the uploads playlist into a stable model."""
    hook = YouTubeHook()
    request = mocker.patch.object(
        hook,
        "_request",
        return_value={
            "items": [
                {
                    "id": "UCabc",
                    "snippet": {
                        "title": "Channel",
                        "description": "Description",
                        "publishedAt": "2020-01-01T00:00:00Z",
                    },
                    "contentDetails": {"relatedPlaylists": {"uploads": "UUabc"}},
                }
            ]
        },
    )

    channel = hook.get_channel("UCabc")

    assert channel.channel_id == "UCabc"
    assert channel.uploads_playlist_id == "UUabc"
    assert channel.schema_version == "1.0"
    assert request.call_args.args[0] == "channels"


def test_get_channel_by_handle_resolves_permanent_channel_id(mocker) -> None:
    """A readable handle is resolved through channels.list(forHandle=...)."""
    hook = YouTubeHook()
    request = mocker.patch.object(
        hook,
        "_request",
        return_value={
            "items": [
                {
                    "id": "UCkvZ2usiWOy1sfYmNfY9Pdw",
                    "snippet": {
                        "title": "Readable Channel",
                        "publishedAt": "2020-01-01T00:00:00Z",
                    },
                    "contentDetails": {"relatedPlaylists": {"uploads": "UUkvZ2usiWOy1sfYmNfY9Pdw"}},
                }
            ]
        },
    )

    channel = hook.get_channel_by_handle("@readable.channel")

    assert channel.channel_id == "UCkvZ2usiWOy1sfYmNfY9Pdw"
    assert request.call_args.args == (
        "channels",
        {
            "part": "snippet,contentDetails",
            "forHandle": "readable.channel",
            "maxResults": 1,
        },
    )


def test_get_videos_batches_and_preserves_requested_order(mocker) -> None:
    """Video metadata is normalized and returned in caller order."""
    hook = YouTubeHook()
    mocker.patch.object(
        hook,
        "_request",
        return_value={
            "items": [
                _video_payload("video2", "2026-08-18T02:00:00Z", duration="PT1H2M3.5S"),
                _video_payload("video1", "2026-08-18T01:00:00Z"),
            ]
        },
    )

    videos = hook.get_videos(["video1", "video2", "video1"])

    assert [video.video_id for video in videos] == ["video1", "video2"]
    assert videos[1].duration_ms == 3_723_500
    assert str(videos[0].thumbnail_url) == "https://img.example/video1.jpg"


def test_http_error_does_not_expose_api_key(mocker) -> None:
    """Sanitized exceptions never include the credential-bearing request URL."""
    hook = YouTubeHook()
    hook._config = YouTubeConnectionConfig(
        api_key="super-secret",
        api_base_url="https://youtube.example/v3",
        timeout=10,
        proxies=None,
        max_retries=0,
        retry_delay=0,
    )
    response = Mock(status_code=403)
    response.json.return_value = {"error": {"message": "Quota exceeded", "errors": [{"reason": "quotaExceeded"}]}}
    session = Mock()
    session.get.return_value = response
    mocker.patch.object(hook, "get_conn", return_value=session)

    with pytest.raises(AirflowException) as error:
        hook._request("videos", {"part": "id", "id": "video1"})

    assert "HTTP 403" in str(error.value)
    assert "super-secret" not in str(error.value)


def _video_payload(video_id: str, published_at: str, *, duration: str = "PT30S") -> dict[str, object]:
    return {
        "id": video_id,
        "snippet": {
            "channelId": "UCabc",
            "channelTitle": "Channel",
            "title": f"Title {video_id}",
            "description": "Description",
            "publishedAt": published_at,
            "thumbnails": {"high": {"url": f"https://img.example/{video_id}.jpg"}},
            "defaultAudioLanguage": "en",
        },
        "contentDetails": {"duration": duration},
    }
