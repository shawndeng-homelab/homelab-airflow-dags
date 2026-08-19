"""Tests for Bark provider discovery metadata."""

from homelab_airflow_bark.get_provider_info import get_provider_info


def test_provider_registers_notifier_hook_and_connection() -> None:
    """Advertise all Bark Airflow integration components."""
    provider_info = get_provider_info()

    assert provider_info["package-name"] == "homelab-airflow-bark"
    assert provider_info["connection-types"][0]["connection-type"] == "bark"
    assert provider_info["connection-types"][0]["hook-class-name"] == "homelab_airflow_bark.hooks.BarkHook"
    assert provider_info["notifications"] == ["homelab_airflow_bark.notifications.BarkNotifier"]
