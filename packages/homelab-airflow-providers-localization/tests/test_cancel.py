"""Tests for Localization Gateway job cancellation."""

from homelab_airflow_providers_localization.hooks.localization import LocalizationHook


def test_cancel_job_uses_normalized_contract(mocker) -> None:
    """Cancel through the generic job endpoint and validate its response."""
    hook = LocalizationHook()
    request = mocker.patch.object(
        hook,
        "_request",
        return_value={"job_id": "job-1", "job_type": "download", "status": "cancelled"},
    )

    job = hook.cancel_job("job/1")

    assert job.status == "cancelled"
    request.assert_called_once_with("POST", "/v1/jobs/job%2F1/cancel")
