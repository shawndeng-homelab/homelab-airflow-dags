"""Tests for normalized localization jobs."""

import pytest
from airflow.exceptions import AirflowException
from homelab_airflow_providers_localization.models import LocalizationJob


def test_job_payload_is_normalized() -> None:
    """Service aliases normalize into the stable public model."""
    job = LocalizationJob.from_payload(
        {
            "id": "job-1",
            "type": "transcribe",
            "status": "succeeded",
            "output": {"transcript_uri": "s3://media/transcript.json"},
        }
    )

    assert job.job_id == "job-1"
    assert job.is_terminal
    assert job.as_dict()["output"] == {"transcript_uri": "s3://media/transcript.json"}


def test_unknown_job_status_is_rejected() -> None:
    """Unknown service states fail instead of silently hanging."""
    with pytest.raises(AirflowException, match="unsupported status"):
        LocalizationJob.from_payload({"job_id": "job-1", "job_type": "download", "status": "mystery"})
