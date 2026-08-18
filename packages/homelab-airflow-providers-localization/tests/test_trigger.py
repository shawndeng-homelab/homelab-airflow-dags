"""Tests for the deferrable localization trigger."""

from homelab_airflow_providers_localization.triggers.localization import LocalizationJobTrigger


def test_trigger_serializes_without_credentials() -> None:
    """Serialized trigger state references a Connection but contains no secret."""
    trigger = LocalizationJobTrigger(job_id="job-1", poll_interval=5)

    classpath, payload = trigger.serialize()

    assert classpath.endswith("LocalizationJobTrigger")
    assert payload == {
        "job_id": "job-1",
        "localization_conn_id": "localization_default",
        "poll_interval": 5,
    }
