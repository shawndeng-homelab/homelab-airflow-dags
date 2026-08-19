"""Tests for playlist pagination and time-window semantics."""

from datetime import UTC
from datetime import datetime

from homelab_airflow_providers_youtube.hooks import YouTubeHook
from homelab_video_contracts import YouTubeVideo


def test_playlist_paginates_until_window_matches_are_found(mocker) -> None:
    """Filtering is inclusive after and exclusive before across pages."""
    hook = YouTubeHook()
    pages = [
        {
            "items": [
                {"contentDetails": {"videoId": "at-before"}},
                {"contentDetails": {"videoId": "inside"}},
            ],
            "nextPageToken": "page-2",
        },
        {
            "items": [
                {"contentDetails": {"videoId": "at-after"}},
                {"contentDetails": {"videoId": "too-old"}},
            ]
        },
    ]
    request = mocker.patch.object(hook, "_request", side_effect=pages)
    timestamps = {
        "at-before": "2026-08-19T00:00:00+00:00",
        "inside": "2026-08-18T12:00:00+00:00",
        "at-after": "2026-08-18T00:00:00+00:00",
        "too-old": "2026-08-17T23:59:59+00:00",
    }
    mocker.patch.object(
        hook,
        "get_videos",
        side_effect=lambda ids: [_video(video_id, timestamps[video_id]) for video_id in ids],
    )

    videos = hook.list_playlist_videos(
        "UUabc",
        published_after="2026-08-18T00:00:00Z",
        published_before="2026-08-19T00:00:00Z",
        max_results=2,
    )

    assert [video.video_id for video in videos] == ["inside", "at-after"]
    assert request.call_count == 2
    assert request.call_args_list[1].args[1]["pageToken"] == "page-2"


def test_playlist_rejects_naive_window() -> None:
    """Airflow windows must be timezone-aware to avoid ambiguous filtering."""
    hook = YouTubeHook()

    try:
        hook.list_playlist_videos("UUabc", published_after=datetime(2026, 8, 18), max_results=1)
    except ValueError as error:
        assert "timezone" in str(error)
    else:
        raise AssertionError("Expected a timezone validation error")


def _video(video_id: str, published_at: str) -> YouTubeVideo:
    return YouTubeVideo(
        video_id=video_id,
        channel_id="UCabc",
        title=video_id,
        published_at=datetime.fromisoformat(published_at).astimezone(UTC),
        source_url=f"https://www.youtube.com/watch?v={video_id}",
    )
