"""Dataset outlet configuration shared by the YouTube operator and sensor."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from airflow.datasets import Dataset
from airflow.datasets import DatasetAlias
from airflow.utils.context import Context
from homelab_video_contracts import YouTubeVideo

from homelab_airflow_providers_youtube.datasets import channel_event_extra
from homelab_airflow_providers_youtube.datasets import youtube_channel_uploads_dataset


YouTubeOutlet = Dataset | DatasetAlias


def configure_outlet(
    channel_id: str,
    outlet: YouTubeOutlet | None,
    declared_outlets: Sequence[Any] | None,
) -> tuple[YouTubeOutlet | None, list[Any]]:
    """Resolve a static Dataset or retain an explicit DatasetAlias."""
    outlets = list(declared_outlets or [])
    resolved = outlet
    if resolved is None and not _is_template(channel_id):
        resolved = youtube_channel_uploads_dataset(channel_id)
    if resolved is not None and resolved not in outlets:
        outlets.append(resolved)
    return resolved, outlets


def emit_channel_event(
    context: Context,
    *,
    outlet: YouTubeOutlet | None,
    channel_id: str,
    videos: Sequence[YouTubeVideo],
    published_after: datetime | None,
    published_before: datetime | None,
) -> None:
    """Attach compact metadata only when discovery produced videos."""
    if outlet is None or not videos:
        return
    extra = channel_event_extra(
        videos,
        published_after=published_after,
        published_before=published_before,
    )
    accessor = context["outlet_events"][outlet]
    if isinstance(outlet, DatasetAlias):
        accessor.add(youtube_channel_uploads_dataset(channel_id), extra=extra)
    else:
        accessor.extra = extra


def _is_template(value: str) -> bool:
    return "{{" in value or "{%" in value
