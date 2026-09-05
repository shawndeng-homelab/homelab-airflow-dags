"""Download one EODHD option EOD partition to a local filesystem store.

Example (PowerShell)::

    $env:EODHD_API_TOKEN = "your-token"
    uv run python packages/homelab-airflow-providers-financial-data/examples/download_options_to_local.py `
        --symbol AAPL --quote-date 2025-01-02
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from homelab_airflow_providers_financial_data.client import EodhdClient
from homelab_airflow_providers_financial_data.ingestion import EodhdOptionsIngestion
from homelab_airflow_providers_financial_data.ingestion import new_storage_target
from homelab_airflow_providers_financial_data.models import EodhdOptionEodRequest
from homelab_airflow_providers_financial_data.storage import LocalFilesystemStore


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse the intentionally small local-download command line."""
    parser = argparse.ArgumentParser(description="Download EODHD option EOD data to a local directory.")
    parser.add_argument("--symbol", required=True, help="US underlying symbol, for example AAPL or SPY.")
    parser.add_argument("--quote-date", required=True, type=date.fromisoformat, help="EOD partition date (YYYY-MM-DD).")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(".local-financial-data"),
        help="Local object-store root (default: .local-financial-data).",
    )
    parser.add_argument("--bucket", default="local-bucket", help="Logical bucket directory (default: local-bucket).")
    parser.add_argument("--prefix", default="financial-data", help="Object key prefix (default: financial-data).")
    parser.add_argument("--run-id", help="Optional immutable run ID; generated when omitted.")
    parser.add_argument(
        "--replace", action="store_true", help="Publish a new current version if this partition exists."
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Download, normalize, and publish one local EOD option partition."""
    args = parse_args(argv)
    request = EodhdOptionEodRequest(
        underlying_symbol=args.symbol,
        quote_date=args.quote_date,
        replace=args.replace,
        run_id=args.run_id,
    )
    target = new_storage_target(args.bucket, args.prefix, args.run_id)
    store = LocalFilesystemStore(args.output_dir)
    with EodhdClient.from_environment() as client:
        manifest = EodhdOptionsIngestion(client, store).run(request, target)

    print(f"run_id: {manifest.run_id}")
    print(f"quote_date: {manifest.quote_date.isoformat()}")
    print(f"underlying_symbol: {manifest.underlying_symbol}")
    print(f"accepted_records: {manifest.quality_report.accepted_records}")
    print(f"rejected_records: {manifest.quality_report.rejected_records}")
    print(f"duplicate_records: {manifest.quality_report.duplicate_records}")
    for artifact in manifest.curated_artifacts:
        print(f"curated_parquet: {artifact.uri}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
