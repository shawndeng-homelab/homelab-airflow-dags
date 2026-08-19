"""Hook for the homelab localization service REST API."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import requests
from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook
from homelab_video_contracts.jobs import LocalizationJobRequest
from pydantic import ValidationError

from homelab_airflow_providers_localization.models import LocalizationJob
from homelab_airflow_providers_localization.models import parse_localization_job


@dataclass(frozen=True, slots=True)
class LocalizationConnectionConfig:
    """Resolved service settings shared with the async trigger."""

    base_url: str
    headers: dict[str, str]
    timeout: float
    verify_tls: bool


class LocalizationHook(BaseHook):
    """Submit and inspect asynchronous localization jobs."""

    conn_name_attr = "localization_conn_id"
    default_conn_name = "localization_default"
    conn_type = "localization"
    hook_name = "Video Localization"

    def __init__(self, localization_conn_id: str = default_conn_name) -> None:
        """Initialize the hook with an Airflow Connection ID."""
        super().__init__()
        self.localization_conn_id = localization_conn_id

    @classmethod
    def get_ui_field_behaviour(cls) -> dict[str, Any]:
        """Describe how the connection form maps to the service."""
        return {
            "hidden_fields": ["schema", "login", "port"],
            "relabeling": {"host": "Base URL", "password": "API token"},
            "placeholders": {
                "host": "https://localization.example.internal",
                "password": "Bearer token (optional)",
                "extra": "JSON object with timeout and verify_tls",
            },
        }

    def get_conn(self) -> requests.Session:
        """Return an authenticated HTTP session."""
        config = self.get_connection_config()
        session = requests.Session()
        session.headers.update(config.headers)
        return session

    def get_connection_config(self) -> LocalizationConnectionConfig:
        """Resolve and validate the Airflow connection."""
        connection = self.get_connection(self.localization_conn_id)
        if not connection.host:
            raise AirflowException(f"Connection {self.localization_conn_id!r} must define a base URL in Host")

        extra = connection.extra_dejson
        timeout = float(extra.get("timeout", 30))
        if timeout <= 0:
            raise AirflowException("Localization connection timeout must be greater than zero")
        verify_tls = extra.get("verify_tls", True)
        if not isinstance(verify_tls, bool):
            raise AirflowException("Localization connection verify_tls must be a boolean")

        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if connection.password:
            headers["Authorization"] = f"Bearer {connection.password}"
        return LocalizationConnectionConfig(
            base_url=connection.host.rstrip("/"),
            headers=headers,
            timeout=timeout,
            verify_tls=verify_tls,
        )

    def submit_job(
        self,
        *,
        job_type: str,
        input_uri: str,
        output_prefix: str,
        parameters: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> LocalizationJob:
        """Validate and submit a job, optionally with an idempotency key."""
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        try:
            request = LocalizationJobRequest(
                job_type=job_type,
                input_uri=input_uri,
                output_prefix=output_prefix,
                parameters=parameters or {},
            )
        except ValidationError as error:
            raise AirflowException("Invalid localization job request") from error

        payload = request.model_dump(mode="json")
        response = self._request("POST", "/v1/jobs", json=payload, headers=headers)
        return parse_localization_job(response)

    def get_job(self, job_id: str) -> LocalizationJob:
        """Fetch a job by ID."""
        if not job_id:
            raise AirflowException("job_id is required")
        safe_job_id = quote(job_id, safe="")
        return parse_localization_job(self._request("GET", f"/v1/jobs/{safe_job_id}"))

    def cancel_job(self, job_id: str) -> LocalizationJob:
        """Request cancellation and return the normalized job state."""
        if not job_id:
            raise AirflowException("job_id is required")
        safe_job_id = quote(job_id, safe="")
        response = self._request("POST", f"/v1/jobs/{safe_job_id}/cancel")
        return parse_localization_job(response)

    def wait_for_job(self, job_id: str, *, poll_interval: float) -> LocalizationJob:
        """Poll synchronously until a job reaches a terminal state."""
        while True:
            job = self.get_job(job_id)
            if job.is_terminal:
                return job
            time.sleep(poll_interval)

    def test_connection(self) -> tuple[bool, str]:
        """Test the configured health endpoint."""
        try:
            self._request("GET", "/health")
        except AirflowException as error:
            return False, str(error)
        return True, "Localization service is reachable"

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> object:
        config = self.get_connection_config()
        try:
            response = self.get_conn().request(
                method,
                f"{config.base_url}{path}",
                json=json,
                headers=headers,
                timeout=config.timeout,
                verify=config.verify_tls,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as error:
            status = error.response.status_code if error.response is not None else None
            detail = f"HTTP {status}" if status is not None else error.__class__.__name__
            raise AirflowException(f"Localization service request failed: {detail}") from error
        except ValueError as error:
            raise AirflowException("Localization service returned invalid JSON") from error
