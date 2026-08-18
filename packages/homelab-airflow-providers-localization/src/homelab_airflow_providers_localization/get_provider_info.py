"""Apache Airflow provider discovery metadata."""

from typing import Any


def get_provider_info() -> dict[str, Any]:
    """Return metadata consumed by Airflow's provider manager."""
    integration = "Video Localization"
    package = "homelab_airflow_providers_localization"
    return {
        "package-name": "homelab-airflow-providers-localization",
        "name": integration,
        "description": "Submit and monitor asynchronous video localization jobs.",
        "connection-types": [
            {
                "hook-class-name": f"{package}.hooks.localization.LocalizationHook",
                "connection-type": "localization",
            }
        ],
        "hooks": [{"integration-name": integration, "python-modules": [f"{package}.hooks.localization"]}],
        "operators": [{"integration-name": integration, "python-modules": [f"{package}.operators.localization"]}],
        "triggers": [{"integration-name": integration, "python-modules": [f"{package}.triggers.localization"]}],
    }
