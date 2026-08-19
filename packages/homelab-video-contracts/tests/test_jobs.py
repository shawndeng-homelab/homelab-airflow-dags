"""Tests for asynchronous localization job contracts."""

from datetime import UTC
from datetime import datetime

import pytest
from homelab_video_contracts.jobs import JobError
from homelab_video_contracts.jobs import JobStatus
from homelab_video_contracts.jobs import JobType
from homelab_video_contracts.jobs import LocalizationJob
from homelab_video_contracts.jobs import LocalizationJobRequest
from pydantic import ValidationError


def test_job_normalizes_gateway_aliases() -> None:
    """Accept gateway id and type aliases while emitting canonical fields."""
    job = LocalizationJob.from_payload(
        {
            "id": "job-1",
            "type": "transcribe",
            "status": "succeeded",
            "output": {"transcript_uri": "s3://bucket/transcript.json"},
        }
    )

    assert job.job_id == "job-1"
    assert job.job_type is JobType.TRANSCRIBE
    assert job.status is JobStatus.SUCCEEDED
    assert job.is_terminal
    assert job.as_dict()["job_type"] == "transcribe"


def test_failed_job_requires_structured_error() -> None:
    """Make failure classification mandatory for retry decisions."""
    with pytest.raises(ValidationError, match="failed job must contain an error"):
        LocalizationJob(job_id="job-1", job_type=JobType.DOWNLOAD, status=JobStatus.FAILED)

    job = LocalizationJob(
        job_id="job-1",
        job_type=JobType.DOWNLOAD,
        status=JobStatus.FAILED,
        error=JobError(code="download_failed", message="yt-dlp exited", retryable=True),
    )
    assert job.error is not None
    assert job.error.retryable is True


def test_job_request_rejects_presigned_output_prefix() -> None:
    """Keep expiring presigned URLs outside durable job contracts."""
    with pytest.raises(ValidationError, match="query"):
        LocalizationJobRequest(
            job_type=JobType.RENDER_VIDEO,
            input_uri="s3://bucket/source.mp4",
            output_prefix="s3://bucket/render/final.mp4?signature=secret",
        )


def test_job_rejects_naive_timestamp() -> None:
    """Require timezone-aware timestamps across service boundaries."""
    with pytest.raises(ValidationError, match="timezone"):
        LocalizationJob(
            job_id="job-1",
            job_type=JobType.DOWNLOAD,
            status=JobStatus.RUNNING,
            created_at=datetime(2026, 8, 19),
        )

    job = LocalizationJob(
        job_id="job-1",
        job_type=JobType.DOWNLOAD,
        status=JobStatus.RUNNING,
        created_at=datetime(2026, 8, 19, tzinfo=UTC),
    )
    assert job.is_terminal is False
