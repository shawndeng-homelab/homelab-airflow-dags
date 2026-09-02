"""Apache Airflow provider discovery metadata."""

from typing import Any


def get_provider_info() -> dict[str, Any]:
    """Return metadata consumed by Airflow's provider manager."""
    package = "homelab_airflow_providers_financial_data"
    return {
        "package-name": "homelab-airflow-providers-financial-data",
        "name": "Financial Data",
        "description": "Ingest EODHD financial market data into S3.",
        "connection-types": [{"hook-class-name": f"{package}.hooks.EodhdHook", "connection-type": "eodhd"}],
        "hooks": [{"integration-name": "EODHD", "python-modules": [f"{package}.hooks"]}],
        "operators": [{"integration-name": "EODHD", "python-modules": [f"{package}.operators"]}],
    }
