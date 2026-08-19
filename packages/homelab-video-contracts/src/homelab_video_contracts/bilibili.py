"""Bilibili publication result contracts."""

from __future__ import annotations

from typing import Annotated

from pydantic import AnyHttpUrl
from pydantic import Field

from homelab_video_contracts.base import AwareDatetime
from homelab_video_contracts.base import PositiveInt
from homelab_video_contracts.base import VersionedContract


class BilibiliPublishResult(VersionedContract):
    """Stable identifiers returned after a successful Bilibili submission."""

    aid: PositiveInt
    bvid: Annotated[str, Field(min_length=1)]
    url: AnyHttpUrl
    published_at: AwareDatetime
    title: Annotated[str, Field(min_length=1)]
