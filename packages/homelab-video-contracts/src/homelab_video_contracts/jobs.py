"""Asynchronous localization job contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated
from typing import Any

from pydantic import AliasChoices
from pydantic import Field
from pydantic import model_validator

from homelab_video_contracts.base import AwareDatetime
from homelab_video_contracts.base import S3Uri
from homelab_video_contracts.base import VersionedContract


class JobType(StrEnum):
    """Supported localization pipeline stages."""

    DOWNLOAD = "download"
    TRANSCRIBE = "transcribe"
    TRANSLATE_SUBTITLES = "translate_subtitles"
    SEPARATE_AUDIO = "separate_audio"
    SYNTHESIZE_SPEECH = "synthesize_speech"
    RENDER_VIDEO = "render_video"
    MEDIA_QUALITY_CHECK = "media_quality_check"


class JobStatus(StrEnum):
    """Normalized status shared by every service adapter."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_JOB_STATUSES = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED})


class JobError(VersionedContract):
    """A safe, structured error returned by a localization adapter."""

    code: Annotated[str, Field(min_length=1)]
    message: Annotated[str, Field(min_length=1)]
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class LocalizationJobRequest(VersionedContract):
    """A generic request accepted by the Localization Gateway."""

    job_type: JobType
    input_uri: Annotated[str, Field(min_length=1)]
    output_prefix: S3Uri
    parameters: dict[str, Any] = Field(default_factory=dict)


class LocalizationJob(VersionedContract):
    """A normalized asynchronous job safe for Airflow XCom."""

    job_id: Annotated[str, Field(min_length=1, validation_alias=AliasChoices("job_id", "id"))]
    job_type: JobType = Field(validation_alias=AliasChoices("job_type", "type"))
    status: JobStatus
    output: dict[str, Any] | None = None
    error: JobError | None = None
    created_at: AwareDatetime | None = None
    updated_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_terminal_result(self) -> LocalizationJob:
        """Require structured errors for failed jobs and forbid them on success."""
        if self.status is JobStatus.FAILED and self.error is None:
            raise ValueError("failed job must contain an error")
        if self.status is JobStatus.SUCCEEDED and self.error is not None:
            raise ValueError("succeeded job must not contain an error")
        return self

    @property
    def is_terminal(self) -> bool:
        """Return whether no further polling is required."""
        return self.status in TERMINAL_JOB_STATUSES

    @classmethod
    def from_payload(cls, payload: object) -> LocalizationJob:
        """Normalize a gateway response, including legacy id and type aliases."""
        return cls.model_validate(payload)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for Airflow XCom and trigger events."""
        return self.model_dump(mode="json")
