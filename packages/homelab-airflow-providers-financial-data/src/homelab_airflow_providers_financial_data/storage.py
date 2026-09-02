"""Immutable raw and curated S3 persistence with manifest-last publication."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC
from datetime import datetime
from io import BytesIO

import polars as pl
from airflow.providers.amazon.aws.hooks.s3 import S3Hook

from homelab_airflow_providers_financial_data.models import Artifact
from homelab_airflow_providers_financial_data.models import IngestionManifest
from homelab_airflow_providers_financial_data.models import RawPage
from homelab_airflow_providers_financial_data.models import StorageTarget


class FinancialDataS3Store:
    """Persist data immutably and make a run visible only through its final manifest."""

    def __init__(self, aws_conn_id: str = "aws_default") -> None:
        """Initialize storage using an Airflow AWS connection."""
        self.hook = S3Hook(aws_conn_id=aws_conn_id)

    def write_raw_page(self, page: RawPage, target: StorageTarget, request_date: str, symbol: str) -> Artifact:
        """Compress and retain one source response page without transformation."""
        key = self._key(
            target,
            f"raw/source=eodhd/dataset=options.eod/ingestion_date={request_date}/underlying_symbol={symbol}/"
            f"run_id={target.run_id}/page-{page.page_number:05d}.json.gz",
        )
        payload = gzip.compress(json.dumps(page.payload, default=str, separators=(",", ":")).encode())
        return self._write_bytes(key, payload, target.bucket, "application/gzip")

    def write_parquet(self, frame: pl.LazyFrame, target: StorageTarget, quote_date: str, symbol: str) -> Artifact:
        """Write Zstandard Parquet under an immutable run identifier."""
        key = self._key(
            target,
            f"curated/dataset=options.eod_quotes/schema_version=1.0/source=eodhd/quote_date={quote_date}/"
            f"underlying_symbol={symbol}/run_id={target.run_id}/part-00001.parquet",
        )
        buffer = BytesIO()
        frame.collect().write_parquet(buffer, compression="zstd")
        return self._write_bytes(key, buffer.getvalue(), target.bucket, "application/vnd.apache.parquet")

    def load_current_manifest(self, target: StorageTarget, quote_date: str, symbol: str) -> IngestionManifest | None:
        """Load the successful manifest, if a prior version exists."""
        key = self._manifest_key(target, quote_date, symbol)
        if not self.hook.check_for_key(key=key, bucket_name=target.bucket):
            return None
        payload = self.hook.read_key(key=key, bucket_name=target.bucket)
        return IngestionManifest.model_validate_json(payload)

    def publish_manifest(self, manifest: IngestionManifest, target: StorageTarget) -> Artifact:
        """Publish the single mutable current pointer after every artifact has succeeded."""
        key = self._manifest_key(target, manifest.quote_date.isoformat(), manifest.underlying_symbol)
        return self._write_bytes(
            key, manifest.model_dump_json().encode(), target.bucket, "application/json", replace=True
        )

    def _manifest_key(self, target: StorageTarget, quote_date: str, symbol: str) -> str:
        return self._key(
            target,
            f"manifests/dataset=options.eod_quotes/source=eodhd/quote_date={quote_date}/"
            f"underlying_symbol={symbol}/current.json",
        )

    @staticmethod
    def _key(target: StorageTarget, suffix: str) -> str:
        return f"{target.normalized_prefix}/{suffix}" if target.normalized_prefix else suffix

    def _write_bytes(self, key: str, data: bytes, bucket: str, content_type: str, replace: bool = False) -> Artifact:
        self.hook.load_bytes(bytes_data=data, key=key, bucket_name=bucket, replace=replace, encrypt=False)
        return Artifact(
            uri=f"s3://{bucket}/{key}",
            key=key,
            content_type=content_type,
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            created_at=datetime.now(UTC),
        )
