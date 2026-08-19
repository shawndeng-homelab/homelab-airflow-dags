"""Tests for stable YouTube Dataset identities."""

import pytest
from homelab_airflow_providers_youtube.datasets import youtube_channel_uploads_dataset
from homelab_airflow_providers_youtube.datasets import youtube_video_dataset


def test_dataset_uris_use_immutable_ids() -> None:
    """Dataset identities contain IDs instead of mutable titles."""
    assert youtube_channel_uploads_dataset("UC_abc-123").uri == "youtube://channel/UC_abc-123/uploads"
    assert youtube_video_dataset("abc_DEF-123").uri == "youtube://video/abc_DEF-123"


def test_dataset_uri_rejects_path_injection() -> None:
    """IDs cannot add URI path or query components."""
    with pytest.raises(ValueError, match="must contain only"):
        youtube_video_dataset("abc/../../key")
