"""Apache Airflow provider discovery metadata."""

from typing import Any


def get_provider_info() -> dict[str, Any]:
    """Return metadata consumed by Airflow's provider manager."""
    package = "homelab_airflow_providers_bilibili"
    integration = "Bilibili"
    return {
        "package-name": "homelab-airflow-providers-bilibili",
        "name": integration,
        "description": "Publish reviewed video artifacts to Bilibili through biliup.",
        "connection-types": [{"hook-class-name": f"{package}.hooks.BilibiliHook", "connection-type": "bilibili"}],
        "hooks": [{"integration-name": integration, "python-modules": [f"{package}.hooks"]}],
        "operators": [{"integration-name": integration, "python-modules": [f"{package}.operators"]}],
        "sensors": [{"integration-name": integration, "python-modules": [f"{package}.sensors"]}],
    }
