"""Stable Airflow Dataset identities and event metadata for YouTube resources."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime

from airflow.datasets import Dataset
from homelab_video_contracts import YouTubeVideo


_YOUTUBE_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def youtube_channel_uploads_dataset(channel_id: str) -> Dataset:
    """Return the stable Dataset for a channel upload stream."""
    validated_id = _validate_id(channel_id, "channel_id")
    return Dataset(f"youtube://channel/{validated_id}/uploads")


def youtube_video_dataset(video_id: str) -> Dataset:
    """Return the stable Dataset for an individual video."""
    validated_id = _validate_id(video_id, "video_id")
    return Dataset(f"youtube://video/{validated_id}")


def video_event_extra(video: YouTubeVideo) -> dict[str, str]:
    """Return compact JSON-safe metadata for a video event."""
    return {
        "video_id": video.video_id,
        "channel_id": video.channel_id,
        "published_at": video.published_at.isoformat(),
        "title": video.title,
        "url": str(video.source_url),
    }


def channel_event_extra(
    videos: Sequence[YouTubeVideo],
    *,
    published_after: datetime | None,
    published_before: datetime | None,
) -> dict[str, object]:
    """Return bounded event metadata for one channel discovery batch."""
    return {
        "video_count": len(videos),
        "video_ids": [video.video_id for video in videos[:50]],
        "published_after": published_after.isoformat() if published_after else None,
        "published_before": published_before.isoformat() if published_before else None,
    }


def _validate_id(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized or not _YOUTUBE_ID.fullmatch(normalized):
        raise ValueError(f"{label} must contain only letters, numbers, underscores, or hyphens")
    return normalized
