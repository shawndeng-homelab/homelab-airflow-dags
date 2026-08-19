"""YouTube source metadata contracts."""

from __future__ import annotations

from typing import Annotated

from pydantic import AnyHttpUrl
from pydantic import Field

from homelab_video_contracts.base import AwareDatetime
from homelab_video_contracts.base import NonNegativeInt
from homelab_video_contracts.base import VersionedContract


class YouTubeVideo(VersionedContract):
    """Stable YouTube metadata used to seed a localization manifest."""

    video_id: Annotated[str, Field(min_length=1)]
    channel_id: Annotated[str, Field(min_length=1)]
    channel_title: str | None = None
    title: Annotated[str, Field(min_length=1)]
    description: str | None = None
    published_at: AwareDatetime
    source_url: AnyHttpUrl
    thumbnail_url: AnyHttpUrl | None = None
    duration_ms: NonNegativeInt | None = None
    default_language: str | None = None
