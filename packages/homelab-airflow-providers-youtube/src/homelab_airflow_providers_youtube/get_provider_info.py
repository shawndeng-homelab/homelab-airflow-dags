"""Apache Airflow provider discovery metadata."""

from typing import Any


def get_provider_info() -> dict[str, Any]:
    """Return metadata consumed by Airflow's provider manager."""
    integration = "YouTube"
    package = "homelab_airflow_providers_youtube"
    return {
        "package-name": "homelab-airflow-providers-youtube",
        "name": integration,
        "description": "Discover public YouTube channels and uploaded videos.",
        "connection-types": [
            {
                "hook-class-name": f"{package}.hooks.YouTubeHook",
                "connection-type": "youtube",
            }
        ],
        "hooks": [{"integration-name": integration, "python-modules": [f"{package}.hooks"]}],
        "operators": [{"integration-name": integration, "python-modules": [f"{package}.operators"]}],
        "sensors": [{"integration-name": integration, "python-modules": [f"{package}.sensors"]}],
    }
