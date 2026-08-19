"""Tests for localization operators."""

import pytest
from airflow.exceptions import AirflowException
from homelab_airflow_providers_localization.operators.localization import SourceSeparationOperator
from homelab_airflow_providers_localization.operators.localization import VideoDownloadOperator


def test_fixed_operator_selects_service_job_type() -> None:
    """A fixed operator submits the expected service job type."""
    operator = SourceSeparationOperator(
        task_id="separate_audio",
        input_uri="s3://media/source.wav",
        output_prefix="s3://media/stems",
    )

    assert operator.job_type == "separate_audio"
    assert operator.deferrable is True


def test_execute_complete_returns_successful_job() -> None:
    """A successful trigger event becomes an XCom-safe dictionary."""
    operator = VideoDownloadOperator(
        task_id="download",
        input_uri="https://youtube.example/watch?v=abc",
        output_prefix="s3://media/jobs/abc",
    )

    result = operator.execute_complete(
        {},
        {
            "status": "success",
            "job": {"job_id": "job-1", "job_type": "download", "status": "succeeded", "output": {}},
        },
    )

    assert result["job_id"] == "job-1"
    assert result["schema_version"] == "1.0"


def test_execute_complete_rejects_failed_job() -> None:
    """A valid structured remote failure fails the Airflow task."""
    operator = VideoDownloadOperator(
        task_id="download",
        input_uri="https://youtube.example/watch?v=abc",
        output_prefix="s3://media/jobs/abc",
    )

    with pytest.raises(AirflowException, match="ended with status"):
        operator.execute_complete(
            {},
            {
                "status": "success",
                "job": {
                    "job_id": "job-1",
                    "job_type": "download",
                    "status": "failed",
                    "error": {
                        "code": "download_failed",
                        "message": "yt-dlp failed",
                        "retryable": True,
                    },
                },
            },
        )
