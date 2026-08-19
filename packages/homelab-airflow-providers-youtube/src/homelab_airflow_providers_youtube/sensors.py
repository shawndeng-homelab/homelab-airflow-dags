"""Reschedule sensor for new YouTube channel uploads."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from airflow.sensors.base import BaseSensorOperator
from airflow.sensors.base import PokeReturnValue
from airflow.utils.context import Context

from homelab_airflow_providers_youtube.events import YouTubeOutlet
from homelab_airflow_providers_youtube.events import configure_outlet
from homelab_airflow_providers_youtube.events import emit_channel_event
from homelab_airflow_providers_youtube.hooks import YouTubeHook
from homelab_airflow_providers_youtube.hooks import coerce_datetime


class YouTubeChannelVideoSensor(BaseSensorOperator):
    """Wait until a channel has an upload in the requested time window."""

    template_fields = (
        "channel_id",
        "published_after",
        "published_before",
        "youtube_conn_id",
    )

    def __init__(
        self,
        *,
        channel_id: str,
        published_after: datetime | str | None = None,
        published_before: datetime | str | None = None,
        max_results: int = 50,
        youtube_conn_id: str = YouTubeHook.default_conn_name,
        outlet: YouTubeOutlet | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a reschedule-mode channel sensor."""
        if not 1 <= max_results <= 200:
            raise ValueError("max_results must be between 1 and 200")
        kwargs.setdefault("mode", "reschedule")
        resolved_outlet, outlets = configure_outlet(channel_id, outlet, kwargs.pop("outlets", None))
        super().__init__(outlets=outlets, **kwargs)
        self.channel_id = channel_id
        self.published_after = published_after
        self.published_before = published_before
        self.max_results = max_results
        self.youtube_conn_id = youtube_conn_id
        self.outlet = resolved_outlet

    def poke(self, context: Context) -> PokeReturnValue:
        """Return matching videos through XCom when discovery succeeds."""
        after = coerce_datetime(self.published_after, "published_after")
        before = coerce_datetime(self.published_before, "published_before")
        videos = YouTubeHook(self.youtube_conn_id).list_channel_videos(
            self.channel_id,
            published_after=after,
            published_before=before,
            max_results=self.max_results,
        )
        if not videos:
            return PokeReturnValue(is_done=False)
        emit_channel_event(
            context,
            outlet=self.outlet,
            channel_id=self.channel_id,
            videos=videos,
            published_after=after,
            published_before=before,
        )
        return PokeReturnValue(
            is_done=True,
            xcom_value=[video.model_dump(mode="json") for video in videos],
        )
