"""A minimal local EODHD options download example; edit the constants below and run it."""

from datetime import date
from pathlib import Path

from homelab_airflow_providers_financial_data.client import EodhdClient
from homelab_airflow_providers_financial_data.ingestion import EodhdOptionsIngestion
from homelab_airflow_providers_financial_data.ingestion import new_storage_target
from homelab_airflow_providers_financial_data.models import EodhdOptionEodRequest
from homelab_airflow_providers_financial_data.storage import LocalFilesystemStore


# Change these values for the partition you want to download.
SYMBOL = "AAPL"
QUOTE_DATE = date(2025, 1, 2)
OUTPUT_DIR = Path(".local-financial-data")


def main() -> None:
    """Download one partition using EODHD_API_TOKEN and print the local result."""
    request = EodhdOptionEodRequest(underlying_symbol=SYMBOL, quote_date=QUOTE_DATE, replace=True)
    target = new_storage_target(bucket="local-bucket", prefix="financial-data")
    store = LocalFilesystemStore(OUTPUT_DIR)
    with EodhdClient.from_environment() as client:
        manifest = EodhdOptionsIngestion(client, store).run(request, target)

    print(f"Downloaded {manifest.underlying_symbol} for {manifest.quote_date.isoformat()}")
    print(f"Accepted records: {manifest.quality_report.accepted_records}")
    print(f"Rejected records: {manifest.quality_report.rejected_records}")
    print(f"Parquet: {manifest.curated_artifacts[0].uri}")


if __name__ == "__main__":
    main()
