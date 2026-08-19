"""Immutable object-storage artifact contracts."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from homelab_video_contracts.base import NonNegativeInt
from homelab_video_contracts.base import S3Uri
from homelab_video_contracts.base import VersionedContract


Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Artifact(VersionedContract):
    """A content-addressable artifact stored in RustFS through the S3 API."""

    uri: S3Uri
    content_type: Annotated[str, Field(min_length=1)]
    size: NonNegativeInt | None = None
    etag: Annotated[str, Field(min_length=1)] | None = None
    version_id: Annotated[str, Field(min_length=1)] | None = None
    sha256: Sha256 | None = None
