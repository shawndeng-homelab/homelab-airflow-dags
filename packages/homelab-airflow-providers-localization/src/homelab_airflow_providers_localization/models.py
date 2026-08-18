"""Stable data models returned by the localization service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from airflow.exceptions import AirflowException


TERMINAL_JOB_STATUSES = frozenset({"succeeded", "failed", "cancelled"})
KNOWN_JOB_STATUSES = TERMINAL_JOB_STATUSES | {"queued", "running"}


@dataclass(frozen=True, slots=True)
class LocalizationJob:
    """A normalized localization job suitable for XCom serialization."""

    job_id: str
    job_type: str
    status: str
    output: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: object) -> LocalizationJob:
        """Validate and normalize a service response."""
        if not isinstance(payload, dict):
            raise AirflowException("Localization service returned a non-object job payload")

        job_id = payload.get("job_id", payload.get("id"))
        job_type = payload.get("job_type", payload.get("type"))
        status = payload.get("status")
        if not isinstance(job_id, str) or not job_id:
            raise AirflowException("Localization job response is missing job_id")
        if not isinstance(job_type, str) or not job_type:
            raise AirflowException("Localization job response is missing job_type")
        if status not in KNOWN_JOB_STATUSES:
            raise AirflowException(f"Localization job {job_id!r} returned unsupported status {status!r}")

        output = payload.get("output")
        error = payload.get("error")
        if output is not None and not isinstance(output, dict):
            raise AirflowException(f"Localization job {job_id!r} returned an invalid output")
        if error is not None and not isinstance(error, dict):
            raise AirflowException(f"Localization job {job_id!r} returned an invalid error")
        return cls(job_id=job_id, job_type=job_type, status=status, output=output, error=error)

    @property
    def is_terminal(self) -> bool:
        """Return whether no further polling is required."""
        return self.status in TERMINAL_JOB_STATUSES

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation for XCom and trigger events."""
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "status": self.status,
            "output": self.output,
            "error": self.error,
        }
