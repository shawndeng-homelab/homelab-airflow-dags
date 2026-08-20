"""Tests for the reschedule-mode YouTube channel sensor."""

from datetime import UTC
from datetime import datetime

from airflow.utils.context import OutletEventAccessors
from homelab_airflow_providers_youtube.hooks import YouTubeHook
from homelab_airflow_providers_youtube.sensors import YouTubeChannelVideoSensor
from homelab_video_contracts import YouTubeVideo


def test_sensor_reschedules_when_no_video_exists(mocker) -> None:
    """An empty discovery does not complete or emit a Dataset event."""
    mocker.patch.object(YouTubeHook, "list_channel_videos", return_value=[])
    sensor = YouTubeChannelVideoSensor(task_id="wait", channel_id="UCabc")
    events = OutletEventAccessors()

    result = sensor.poke(context={"outlet_events": events})

    assert sensor.mode == "reschedule"
    assert result.is_done is False
    assert len(events) == 0


def test_sensor_returns_video_metadata_on_match(mocker) -> None:
    """A matching upload completes the sensor with an XCom-safe value."""
    video = YouTubeVideo(
        video_id="video-1",
        channel_id="UCabc",
        title="Video",
        published_at=datetime(2026, 8, 18, 1, tzinfo=UTC),
        source_url="https://www.youtube.com/watch?v=video-1",
    )
    mocker.patch.object(YouTubeHook, "list_channel_videos", return_value=[video])
    sensor = YouTubeChannelVideoSensor(task_id="wait", channel_id="UCabc")
    events = OutletEventAccessors()

    result = sensor.poke(context={"outlet_events": events})

    assert result.is_done is True
    assert result.xcom_value[0]["video_id"] == "video-1"
    assert events[sensor.outlet].extra["video_count"] == 1
