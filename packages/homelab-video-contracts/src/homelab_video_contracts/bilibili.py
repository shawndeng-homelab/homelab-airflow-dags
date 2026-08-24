"""Bilibili publication request and result contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from typing import Literal

from pydantic import AnyHttpUrl
from pydantic import Field
from pydantic import model_validator

from homelab_video_contracts.artifacts import Artifact
from homelab_video_contracts.base import AwareDatetime
from homelab_video_contracts.base import ContractModel
from homelab_video_contracts.base import PositiveInt
from homelab_video_contracts.base import S3Uri
from homelab_video_contracts.base import VersionedContract


Bvid = Annotated[str, Field(pattern=r"^BV[0-9A-Za-z]+$")]


class BilibiliPublicationStatus(StrEnum):
    """Normalized lifecycle states for a Bilibili archive."""

    SUBMITTED = "submitted"
    REVIEWING = "reviewing"
    PUBLISHED = "published"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class BilibiliPartInput(ContractModel):
    """One video artifact submitted as a稿件分P."""

    video: Artifact
    title: Annotated[str, Field(min_length=1)]
    description: str = ""


class BilibiliPublishSettings(ContractModel):
    """Optional platform settings passed through the biliup adapter."""

    dolby: bool = False
    lossless_music: bool = False
    no_reprint: bool = False
    charging_pay: bool = False
    close_reply: bool = False
    selection_reply: bool = False
    close_danmu: bool = False
    extra_fields: dict[str, object] = Field(default_factory=dict)


class BilibiliUploadRequest(VersionedContract):
    """Complete immutable input for a new Bilibili submission."""

    source_video_id: Annotated[str, Field(min_length=1)]
    parts: tuple[BilibiliPartInput, ...] = Field(min_length=1)
    title: Annotated[str, Field(min_length=1, max_length=80)]
    description: str = ""
    tid: PositiveInt = 171
    tags: tuple[Annotated[str, Field(min_length=1)], ...] = ()
    copyright: Literal[1, 2] = 1
    source_url: str | None = None
    dynamic: str = ""
    cover: Artifact | None = None
    scheduled_at: AwareDatetime | None = None
    settings: BilibiliPublishSettings = Field(default_factory=BilibiliPublishSettings)


class BilibiliAppendRequest(VersionedContract):
    """Input for appending parts to an existing稿件."""

    aid: PositiveInt | None = None
    bvid: Bvid | None = None
    parts: tuple[BilibiliPartInput, ...] = Field(min_length=1)
    expected_part_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_target(self) -> BilibiliAppendRequest:
        """Require an aid or bvid target for archive edits."""
        if self.aid is None and self.bvid is None:
            raise ValueError("append request must contain aid or bvid")
        return self


class BilibiliPartResult(ContractModel):
    """Durable identity of a successfully uploaded part."""

    index: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1)]
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    remote_filename: Annotated[str, Field(min_length=1)]
    cid: PositiveInt | None = None


class BilibiliArchivePart(ContractModel):
    """Remote identity of an existing archive part."""

    index: int = Field(ge=1)
    title: Annotated[str, Field(min_length=1)]
    description: str = ""
    remote_filename: Annotated[str, Field(min_length=1)]
    cid: PositiveInt | None = None


class BilibiliPublishResult(VersionedContract):
    """Stable identifiers returned after a successful Bilibili submission."""

    aid: PositiveInt
    bvid: Bvid
    url: AnyHttpUrl
    published_at: AwareDatetime
    title: Annotated[str, Field(min_length=1)]
    status: BilibiliPublicationStatus = BilibiliPublicationStatus.SUBMITTED
    account_id: Annotated[str, Field(min_length=1)] = "default"
    request_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    parts: tuple[BilibiliPartResult, ...] = ()
    raw_response_uri: S3Uri | None = None


class BilibiliPublicationRecord(VersionedContract):
    """Idempotency and reconciliation record for one source/account/request."""

    source_video_id: Annotated[str, Field(min_length=1)]
    account_id: Annotated[str, Field(min_length=1)]
    request_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    status: BilibiliPublicationStatus = BilibiliPublicationStatus.UNKNOWN
    aid: PositiveInt | None = None
    bvid: Bvid | None = None
    first_submitted_at: AwareDatetime | None = None
    last_checked_at: AwareDatetime | None = None
    parts: tuple[BilibiliPartResult, ...] = ()
    raw_response_uri: S3Uri | None = None


class BilibiliArchiveSnapshot(ContractModel):
    """Remote metadata required to safely perform a full archive edit."""

    aid: PositiveInt
    bvid: Bvid
    title: Annotated[str, Field(min_length=1)]
    description: str = ""
    tid: PositiveInt | None = None
    tags: tuple[str, ...] = ()
    cover: str | None = None
    copyright: Literal[1, 2] = 1
    source_url: str | None = None
    dynamic: str = ""
    settings: BilibiliPublishSettings = Field(default_factory=BilibiliPublishSettings)
    status: BilibiliPublicationStatus = BilibiliPublicationStatus.UNKNOWN
    parts: tuple[BilibiliArchivePart, ...] = ()
    archive: dict[str, object] = Field(default_factory=dict)
    videos: tuple[dict[str, object], ...] = ()
