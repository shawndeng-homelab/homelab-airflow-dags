"""Shared contract test fixtures."""

from datetime import UTC
from datetime import datetime

import pytest
from homelab_video_contracts.artifacts import Artifact
from homelab_video_contracts.youtube import YouTubeVideo


@pytest.fixture
def artifact() -> Artifact:
    """Return a valid immutable RustFS artifact."""
    return Artifact(
        uri="s3://video-localization/youtube/abc/source/video.mp4",
        content_type="video/mp4",
        size=1024,
        etag="etag-1",
        version_id="version-1",
        sha256="a" * 64,
    )


@pytest.fixture
def youtube_video() -> YouTubeVideo:
    """Return stable source metadata for a manifest."""
    return YouTubeVideo(
        video_id="abc",
        channel_id="channel-1",
        title="Example video",
        published_at=datetime(2026, 8, 19, tzinfo=UTC),
        source_url="https://www.youtube.com/watch?v=abc",
        duration_ms=60000,
    )
