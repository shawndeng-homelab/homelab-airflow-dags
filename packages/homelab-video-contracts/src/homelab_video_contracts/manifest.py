"""Video localization manifest contracts."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic import model_validator

from homelab_video_contracts.artifacts import Artifact
from homelab_video_contracts.artifacts import Sha256
from homelab_video_contracts.base import AwareDatetime
from homelab_video_contracts.base import VersionedContract
from homelab_video_contracts.bilibili import BilibiliPublishResult
from homelab_video_contracts.jobs import TERMINAL_JOB_STATUSES
from homelab_video_contracts.jobs import JobError
from homelab_video_contracts.jobs import JobStatus
from homelab_video_contracts.jobs import JobType
from homelab_video_contracts.youtube import YouTubeVideo


ArtifactKey = Annotated[str, Field(min_length=1, pattern=r"^[a-z0-9][a-z0-9._/-]*$")]


class StageRecord(VersionedContract):
    """The latest durable state of one pipeline stage."""

    job_type: JobType
    status: JobStatus
    job_id: Annotated[str, Field(min_length=1)]
    idempotency_key: Annotated[str, Field(min_length=1)]
    input_artifacts: tuple[ArtifactKey, ...] = ()
    output_artifacts: tuple[ArtifactKey, ...] = ()
    parameters_sha256: Sha256
    error: JobError | None = None
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None

    @model_validator(mode="after")
    def validate_state(self) -> StageRecord:
        """Keep timestamps and errors consistent with the normalized status."""
        if self.status in TERMINAL_JOB_STATUSES and self.completed_at is None:
            raise ValueError("terminal stage must contain completed_at")
        if self.status is JobStatus.FAILED and self.error is None:
            raise ValueError("failed stage must contain an error")
        if self.status is JobStatus.SUCCEEDED and self.error is not None:
            raise ValueError("succeeded stage must not contain an error")
        if self.started_at and self.completed_at and self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        return self


class VideoManifest(VersionedContract):
    """The versioned artifact index for one YouTube localization workflow."""

    video_id: Annotated[str, Field(min_length=1)]
    revision: Annotated[int, Field(ge=1)] = 1
    source: YouTubeVideo
    artifacts: dict[ArtifactKey, Artifact] = Field(default_factory=dict)
    stages: dict[JobType, StageRecord] = Field(default_factory=dict)
    publication: BilibiliPublishResult | None = None
    created_at: AwareDatetime
    updated_at: AwareDatetime

    @model_validator(mode="after")
    def validate_index(self) -> VideoManifest:
        """Validate source identity, stage keys, and artifact references."""
        if self.video_id != self.source.video_id:
            raise ValueError("manifest video_id must match source video_id")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at must not precede created_at")

        artifact_keys = set(self.artifacts)
        for job_type, stage in self.stages.items():
            if job_type is not stage.job_type:
                raise ValueError("stage dictionary key must match stage job_type")
            references = {*stage.input_artifacts, *stage.output_artifacts}
            missing = references - artifact_keys
            if missing:
                missing_list = ", ".join(sorted(missing))
                raise ValueError(f"stage references missing artifacts: {missing_list}")
        return self
