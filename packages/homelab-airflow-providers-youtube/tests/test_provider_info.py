"""Tests for Airflow provider discovery metadata."""

from homelab_airflow_providers_youtube.get_provider_info import get_provider_info


def test_provider_info_registers_all_components() -> None:
    """Provider metadata exposes its connection and implemented components."""
    provider_info = get_provider_info()

    assert provider_info["package-name"] == "homelab-airflow-providers-youtube"
    assert provider_info["connection-types"][0]["connection-type"] == "youtube"
    assert provider_info["hooks"]
    assert provider_info["operators"]
    assert provider_info["sensors"]
