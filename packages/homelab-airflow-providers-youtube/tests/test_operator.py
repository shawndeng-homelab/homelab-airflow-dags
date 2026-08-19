"""Tests for the YouTube channel discovery operator."""

from datetime import UTC
from datetime import datetime

from airflow.datasets import DatasetAlias
from airflow.utils.context import OutletEventAccessors
from homelab_airflow_providers_youtube.hooks import YouTubeHook
from homelab_airflow_providers_youtube.operators import YouTubeChannelVideosOperator
from homelab_video_contracts import YouTubeVideo


def test_operator_returns_json_and_emits_bounded_dataset_event(mocker) -> None:
    """A non-empty result updates the static channel Dataset outlet."""
    video = _video()
    mocker.patch.object(YouTubeHook, "list_channel_videos", return_value=[video])
    operator = YouTubeChannelVideosOperator(
        task_id="discover",
        channel_id="UCabc",
        published_after="2026-08-18T00:00:00Z",
        max_results=10,
    )
    events = OutletEventAccessors()

    result = operator.execute({"outlet_events": events})

    assert result[0]["video_id"] == "video-1"
    assert result[0]["published_at"] == "2026-08-18T01:00:00Z"
    assert operator.outlets[0].uri == "youtube://channel/UCabc/uploads"
    assert events[operator.outlet].extra["video_ids"] == ("video-1",)
    assert frozenset(events[operator.outlet].extra.items())


def test_operator_supports_dataset_alias_for_templated_channel() -> None:
    """A runtime channel ID can emit through an explicitly declared alias."""
    alias = DatasetAlias("youtube-runtime-channel")
    operator = YouTubeChannelVideosOperator(
        task_id="discover",
        channel_id="{{ params.channel_id }}",
        outlet=alias,
    )

    assert operator.outlet == alias
    assert alias in operator.outlets


def _video() -> YouTubeVideo:
    return YouTubeVideo(
        video_id="video-1",
        channel_id="UCabc",
        title="Video",
        published_at=datetime(2026, 8, 18, 1, tzinfo=UTC),
        source_url="https://www.youtube.com/watch?v=video-1",
    )
