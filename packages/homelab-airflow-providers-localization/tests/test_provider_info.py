"""Tests for Airflow provider discovery metadata."""

from homelab_airflow_providers_localization.get_provider_info import get_provider_info


def test_provider_info_registers_connection_and_components() -> None:
    """Provider discovery exposes every implemented component category."""
    provider_info = get_provider_info()

    assert provider_info["package-name"] == "homelab-airflow-providers-localization"
    assert provider_info["connection-types"][0]["connection-type"] == "localization"
    assert provider_info["hooks"]
    assert provider_info["operators"]
    assert provider_info["triggers"]
