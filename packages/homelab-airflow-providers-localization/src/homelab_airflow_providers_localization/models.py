"""Airflow boundary helpers for shared localization contracts."""

from airflow.exceptions import AirflowException
from homelab_video_contracts.jobs import JobStatus
from homelab_video_contracts.jobs import JobType
from homelab_video_contracts.jobs import LocalizationJob
from pydantic import ValidationError


def parse_localization_job(payload: object) -> LocalizationJob:
    """Convert invalid gateway responses into a stable Airflow exception."""
    try:
        return LocalizationJob.from_payload(payload)
    except ValidationError as error:
        raise AirflowException("Localization service returned an invalid job payload") from error


__all__ = ["JobStatus", "JobType", "LocalizationJob", "parse_localization_job"]
