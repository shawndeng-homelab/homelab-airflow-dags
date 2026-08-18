"""Tests for the localization service hook."""

from unittest.mock import Mock

from airflow.models.connection import Connection
from homelab_airflow_providers_localization.hooks.localization import LocalizationConnectionConfig
from homelab_airflow_providers_localization.hooks.localization import LocalizationHook


def test_connection_maps_host_password_and_extra(mocker) -> None:
    """Connection fields map to HTTP settings without exposing the token."""
    hook = LocalizationHook()
    mocker.patch.object(
        hook,
        "get_connection",
        return_value=Connection(
            conn_id="localization_default",
            host="https://localization.internal/",
            password="secret-token",
            extra='{"timeout": 12, "verify_tls": false}',
        ),
    )

    config = hook.get_connection_config()

    assert config.base_url == "https://localization.internal"
    assert config.headers["Authorization"] == "Bearer secret-token"
    assert config.timeout == 12
    assert config.verify_tls is False


def test_submit_job_sends_idempotency_key(mocker) -> None:
    """Submission sends a caller-supplied idempotency key."""
    hook = LocalizationHook()
    config = LocalizationConnectionConfig(
        base_url="https://localization.internal",
        headers={"Accept": "application/json"},
        timeout=30,
        verify_tls=True,
    )
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"job_id": "job-1", "job_type": "download", "status": "queued"}
    session = Mock()
    session.request.return_value = response
    mocker.patch.object(hook, "get_connection_config", return_value=config)
    mocker.patch.object(hook, "get_conn", return_value=session)

    job = hook.submit_job(
        job_type="download",
        input_uri="https://youtube.example/watch?v=abc",
        output_prefix="s3://media/jobs/abc",
        idempotency_key="dag:run:task:-1",
    )

    assert job.job_id == "job-1"
    session.request.assert_called_once()
    assert session.request.call_args.kwargs["headers"] == {"Idempotency-Key": "dag:run:task:-1"}
