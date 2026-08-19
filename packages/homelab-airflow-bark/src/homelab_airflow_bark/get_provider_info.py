"""Apache Airflow provider discovery metadata."""

from typing import Any


def get_provider_info() -> dict[str, Any]:
    """Return metadata consumed by Airflow's provider manager."""
    integration = "Bark"
    package = "homelab_airflow_bark"
    return {
        "package-name": "homelab-airflow-bark",
        "name": integration,
        "description": "Send Airflow lifecycle notifications through Bark.",
        "connection-types": [{"hook-class-name": f"{package}.hooks.BarkHook", "connection-type": "bark"}],
        "hooks": [{"integration-name": integration, "python-modules": [f"{package}.hooks"]}],
        "operators": [{"integration-name": integration, "python-modules": [f"{package}.operators"]}],
        "notifications": [f"{package}.notifications.BarkNotifier"],
    }
