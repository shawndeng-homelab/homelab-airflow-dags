"""Tests for the YouTube channel update DAG helpers."""

import pytest

from homelab_airflow_dags.dags.youtube_channel_updates import normalize_channel_references


def test_normalize_channel_references_trims_and_deduplicates() -> None:
    """Normalize repeated channel handles and IDs without changing their order."""
    assert normalize_channel_references([" @EarnMoar ", "UC123", "@EarnMoar", "UC123 "]) == [
        "@EarnMoar",
        "UC123",
    ]


@pytest.mark.parametrize("channels", [None, {}, [], [""], ["   "], [123]])
def test_normalize_channel_references_rejects_invalid_values(channels: object) -> None:
    """Reject values that cannot represent a non-empty channel reference list."""
    with pytest.raises(ValueError, match="youtube_watched_channels"):
        normalize_channel_references(channels)
