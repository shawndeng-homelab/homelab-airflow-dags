"""Tests for the Localization Provider contract boundary."""

import pytest
from airflow.exceptions import AirflowException
from homelab_airflow_providers_localization.models import JobStatus
from homelab_airflow_providers_localization.models import parse_localization_job


def test_job_payload_is_normalized() -> None:
    """Normalize gateway aliases through the shared contract."""
    job = parse_localization_job(
        {
            "id": "job-1",
            "type": "transcribe",
            "status": "succeeded",
            "output": {"transcript_uri": "s3://media/transcript.json"},
        }
    )

    assert job.job_id == "job-1"
    assert job.status is JobStatus.SUCCEEDED
    assert job.is_terminal
    assert job.as_dict()["output"] == {"transcript_uri": "s3://media/transcript.json"}


def test_unknown_job_status_is_rejected_at_airflow_boundary() -> None:
    """Convert shared-contract validation failures into AirflowException."""
    with pytest.raises(AirflowException, match="invalid job payload"):
        parse_localization_job({"job_id": "job-1", "job_type": "download", "status": "mystery"})
