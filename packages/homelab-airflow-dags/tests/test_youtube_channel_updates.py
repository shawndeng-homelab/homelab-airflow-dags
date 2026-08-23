"""Tests for the YouTube channel update DAG helpers."""

import pytest
from homelab_airflow_dags.dags.youtube_channel_updates import normalize_channel_references
from homelab_airflow_dags.dags.youtube_channel_updates import youtube_channel_updates


def test_normalize_channel_references_trims_and_deduplicates() -> None:
    """Normalize repeated channel handles and IDs without changing their order."""
    assert normalize_channel_references([" @EarnMoar ", "UC123", "@earnmoar", "UC123 "]) == [
        "@EarnMoar",
        "UC123",
    ]


@pytest.mark.parametrize("channels", [None, {}, [], [""], ["   "], [123]])
def test_normalize_channel_references_rejects_invalid_values(channels: object) -> None:
    """Reject values that cannot represent a non-empty channel reference list."""
    with pytest.raises(ValueError, match="youtube_watched_channels"):
        normalize_channel_references(channels)


def test_discovery_task_does_not_declare_unused_dataset_alias() -> None:
    """Do not emit through an alias that has no metadata-database consumer record."""
    assert youtube_channel_updates.get_task("discover_channel_videos").outlets == []
