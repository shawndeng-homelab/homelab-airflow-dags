"""Tests for the durable video artifact manifest."""

from datetime import UTC
from datetime import datetime

import pytest
from homelab_video_contracts.artifacts import Artifact
from homelab_video_contracts.jobs import JobStatus
from homelab_video_contracts.jobs import JobType
from homelab_video_contracts.manifest import StageRecord
from homelab_video_contracts.manifest import VideoManifest
from homelab_video_contracts.youtube import YouTubeVideo
from pydantic import ValidationError


def make_download_stage() -> StageRecord:
    """Return a successful, reproducible download stage."""
    timestamp = datetime(2026, 8, 19, 4, 0, tzinfo=UTC)
    return StageRecord(
        job_type=JobType.DOWNLOAD,
        status=JobStatus.SUCCEEDED,
        job_id="job-download-1",
        idempotency_key="youtube:abc:download:v1",
        output_artifacts=("source.video",),
        parameters_sha256="b" * 64,
        started_at=timestamp,
        completed_at=timestamp,
    )


def test_manifest_round_trip_indexes_stage_artifacts(
    artifact: Artifact,
    youtube_video: YouTubeVideo,
) -> None:
    """Persist one immutable source artifact and its successful stage state."""
    timestamp = datetime(2026, 8, 19, 4, 0, tzinfo=UTC)
    manifest = VideoManifest(
        video_id="abc",
        source=youtube_video,
        artifacts={"source.video": artifact},
        stages={JobType.DOWNLOAD: make_download_stage()},
        created_at=timestamp,
        updated_at=timestamp,
    )

    restored = VideoManifest.model_validate_json(manifest.model_dump_json())
    assert restored == manifest
    assert restored.artifacts["source.video"].uri.endswith("/source/video.mp4")
    assert restored.stages[JobType.DOWNLOAD].status is JobStatus.SUCCEEDED


def test_manifest_rejects_missing_artifact_reference(youtube_video: YouTubeVideo) -> None:
    """Prevent stages from claiming outputs that the manifest cannot resolve."""
    timestamp = datetime(2026, 8, 19, 4, 0, tzinfo=UTC)
    with pytest.raises(ValidationError, match="missing artifacts"):
        VideoManifest(
            video_id="abc",
            source=youtube_video,
            stages={JobType.DOWNLOAD: make_download_stage()},
            created_at=timestamp,
            updated_at=timestamp,
        )


def test_manifest_rejects_source_identity_mismatch(youtube_video: YouTubeVideo) -> None:
    """Bind each manifest to exactly one immutable YouTube video ID."""
    timestamp = datetime(2026, 8, 19, 4, 0, tzinfo=UTC)
    with pytest.raises(ValidationError, match="must match source"):
        VideoManifest(
            video_id="different",
            source=youtube_video,
            created_at=timestamp,
            updated_at=timestamp,
        )


def test_terminal_stage_requires_completion_timestamp() -> None:
    """Distinguish terminal durable state from an incomplete status update."""
    with pytest.raises(ValidationError, match="completed_at"):
        StageRecord(
            job_type=JobType.DOWNLOAD,
            status=JobStatus.SUCCEEDED,
            job_id="job-download-1",
            idempotency_key="youtube:abc:download:v1",
            parameters_sha256="b" * 64,
        )
