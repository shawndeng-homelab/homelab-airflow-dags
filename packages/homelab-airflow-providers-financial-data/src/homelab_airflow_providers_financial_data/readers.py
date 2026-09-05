"""Consumer-oriented access to published financial-data manifests."""

from __future__ import annotations

from typing import Protocol

import polars as pl

from homelab_airflow_providers_financial_data.models import IngestionManifest
from homelab_airflow_providers_financial_data.models import StorageTarget


class ManifestStore(Protocol):
    """The minimal read contract required by downstream consumers."""

    def load_current_manifest(self, target: StorageTarget, quote_date: str, symbol: str) -> IngestionManifest | None:
        """Return the manifest addressed by the current pointer, if one exists."""


class FinancialDataManifestReader:
    """Resolve only successfully published curated artifacts for a data partition."""

    def __init__(self, store: ManifestStore) -> None:
        """Initialize the reader with an S3 or local storage adapter."""
        self.store = store

    def load_current(self, target: StorageTarget, quote_date: str, symbol: str) -> IngestionManifest:
        """Return the published manifest or raise a clear partition-not-found error."""
        manifest = self.store.load_current_manifest(target, quote_date, symbol.upper())
        if manifest is None:
            raise FileNotFoundError(f"No published options.eod_quotes manifest for {symbol.upper()} on {quote_date}")
        return manifest

    def scan_current_parquet(self, target: StorageTarget, quote_date: str, symbol: str) -> pl.LazyFrame:
        """Create a lazy scan from only the curated artifacts named by the manifest."""
        manifest = self.load_current(target, quote_date, symbol)
        return pl.scan_parquet([artifact.uri for artifact in manifest.curated_artifacts])
