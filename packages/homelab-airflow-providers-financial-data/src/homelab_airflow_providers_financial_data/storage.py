"""Immutable raw and curated persistence with manifest snapshots and guarded pointers."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC
from datetime import datetime
from io import BytesIO
from pathlib import Path

import polars as pl
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from botocore.exceptions import ClientError

from homelab_airflow_providers_financial_data.models import Artifact
from homelab_airflow_providers_financial_data.models import IngestionManifest
from homelab_airflow_providers_financial_data.models import ManifestPointer
from homelab_airflow_providers_financial_data.models import RawPage
from homelab_airflow_providers_financial_data.models import StorageTarget


class FinancialDataS3Store:
    """Persist immutable objects and conditionally advance the current pointer."""

    def __init__(self, aws_conn_id: str = "aws_default") -> None:
        """Initialize storage through an Airflow AWS connection."""
        self.hook = S3Hook(aws_conn_id=aws_conn_id)

    def write_raw_page(self, page: RawPage, target: StorageTarget, request_date: str, symbol: str) -> Artifact:
        """Persist one compressed source response under its immutable run key."""
        key = self._key(
            target,
            f"raw/source=eodhd/dataset=options.eod/ingestion_date={request_date}/underlying_symbol={symbol}/run_id={target.run_id}/page-{page.page_number:05d}.json.gz",
        )
        return self._write_immutable(
            key,
            gzip.compress(json.dumps(page.payload, default=str, separators=(",", ":")).encode()),
            target.bucket,
            "application/gzip",
        )

    def write_parquet(self, frame: pl.LazyFrame, target: StorageTarget, quote_date: str, symbol: str) -> Artifact:
        """Persist normalized data in an immutable Zstandard Parquet object."""
        key = self._key(
            target,
            f"curated/dataset=options.eod_quotes/schema_version=2.0/source=eodhd/quote_date={quote_date}/underlying_symbol={symbol}/run_id={target.run_id}/part-00001.parquet",
        )
        buffer = BytesIO()
        frame.collect().write_parquet(buffer, compression="zstd")
        return self._write_immutable(key, buffer.getvalue(), target.bucket, "application/vnd.apache.parquet")

    def load_current_manifest(self, target: StorageTarget, quote_date: str, symbol: str) -> IngestionManifest | None:
        """Load the checksum-verified manifest addressed by the current pointer."""
        pointer_key = self._pointer_key(target, quote_date, symbol)
        if not self.hook.check_for_key(key=pointer_key, bucket_name=target.bucket):
            return None
        pointer = ManifestPointer.model_validate_json(self.hook.read_key(key=pointer_key, bucket_name=target.bucket))
        manifest_key = self._manifest_key(target, quote_date, symbol, pointer.run_id)
        payload = self.hook.read_key(key=manifest_key, bucket_name=target.bucket)
        if hashlib.sha256(payload.encode()).hexdigest() != pointer.manifest_sha256:
            raise RuntimeError("Current manifest checksum does not match its pointer")
        return IngestionManifest.model_validate_json(payload)

    def publish_manifest(
        self, manifest: IngestionManifest, target: StorageTarget, expected_current_run_id: str | None
    ) -> Artifact:
        """Save a run snapshot then advance the guarded current pointer."""
        manifest_key = self._manifest_key(
            target, manifest.quote_date.isoformat(), manifest.underlying_symbol, manifest.run_id
        )
        manifest_bytes = manifest.model_dump_json().encode()
        artifact = self._write_immutable(manifest_key, manifest_bytes, target.bucket, "application/json")
        pointer = ManifestPointer(
            quote_date=manifest.quote_date,
            underlying_symbol=manifest.underlying_symbol,
            run_id=manifest.run_id,
            manifest_uri=artifact.uri,
            manifest_sha256=artifact.sha256,
            published_at=manifest.published_at,
        )
        self._advance_pointer(
            self._pointer_key(target, manifest.quote_date.isoformat(), manifest.underlying_symbol),
            pointer.model_dump_json().encode(),
            target.bucket,
            expected_current_run_id,
        )
        return artifact

    def _advance_pointer(self, key: str, data: bytes, bucket: str, expected_run_id: str | None) -> None:
        client = self.hook.get_conn()
        conditions: dict[str, str] = {"IfNoneMatch": "*"}
        if expected_run_id is not None:
            try:
                current = client.get_object(Bucket=bucket, Key=key)
                pointer = ManifestPointer.model_validate_json(current["Body"].read())
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") in {"NoSuchKey", "404"}:
                    raise RuntimeError("Current manifest changed before publication") from None
                raise RuntimeError("Unable to read current manifest pointer") from None
            if pointer.run_id != expected_run_id:
                raise RuntimeError("Current manifest changed before publication")
            conditions = {"IfMatch": current["ETag"]}
        try:
            client.put_object(Bucket=bucket, Key=key, Body=data, ContentType="application/json", **conditions)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in {"PreconditionFailed", "412"}:
                raise RuntimeError("Current manifest changed before publication") from None
            raise RuntimeError("Unable to publish current manifest pointer") from None

    def _write_immutable(self, key: str, data: bytes, bucket: str, content_type: str) -> Artifact:
        self.hook.load_bytes(bytes_data=data, key=key, bucket_name=bucket, replace=False, encrypt=False)
        return _artifact(f"s3://{bucket}/{key}", key, content_type, data)

    def _pointer_key(self, target: StorageTarget, quote_date: str, symbol: str) -> str:
        return self._key(
            target,
            f"manifests/dataset=options.eod_quotes/schema_version=2.0/source=eodhd/quote_date={quote_date}/underlying_symbol={symbol}/current.json",
        )

    def _manifest_key(self, target: StorageTarget, quote_date: str, symbol: str, run_id: str) -> str:
        return self._key(
            target,
            f"manifests/dataset=options.eod_quotes/schema_version=2.0/source=eodhd/quote_date={quote_date}/underlying_symbol={symbol}/runs/{run_id}.json",
        )

    @staticmethod
    def _key(target: StorageTarget, suffix: str) -> str:
        return f"{target.normalized_prefix}/{suffix}" if target.normalized_prefix else suffix


class LocalFilesystemStore:
    """Filesystem adapter mirroring S3 keys, snapshots, and guarded publication."""

    def __init__(self, root: Path) -> None:
        """Initialize an isolated directory used to emulate an object-store bucket."""
        self.root = root.resolve()

    def write_raw_page(self, page: RawPage, target: StorageTarget, request_date: str, symbol: str) -> Artifact:
        """Persist one compressed source response under its immutable run key."""
        key = FinancialDataS3Store._key(
            target,
            f"raw/source=eodhd/dataset=options.eod/ingestion_date={request_date}/underlying_symbol={symbol}/run_id={target.run_id}/page-{page.page_number:05d}.json.gz",
        )
        return self._write_immutable(
            key,
            gzip.compress(json.dumps(page.payload, default=str, separators=(",", ":")).encode()),
            target,
            "application/gzip",
        )

    def write_parquet(self, frame: pl.LazyFrame, target: StorageTarget, quote_date: str, symbol: str) -> Artifact:
        """Persist normalized data in an immutable Zstandard Parquet object."""
        key = FinancialDataS3Store._key(
            target,
            f"curated/dataset=options.eod_quotes/schema_version=2.0/source=eodhd/quote_date={quote_date}/underlying_symbol={symbol}/run_id={target.run_id}/part-00001.parquet",
        )
        buffer = BytesIO()
        frame.collect().write_parquet(buffer, compression="zstd")
        return self._write_immutable(key, buffer.getvalue(), target, "application/vnd.apache.parquet")

    def load_current_manifest(self, target: StorageTarget, quote_date: str, symbol: str) -> IngestionManifest | None:
        """Load the checksum-verified manifest addressed by the current pointer."""
        pointer_path = self._path(target, self._pointer_key(target, quote_date, symbol))
        if not pointer_path.is_file():
            return None
        pointer = ManifestPointer.model_validate_json(pointer_path.read_text())
        payload = self._path(target, self._manifest_key(target, quote_date, symbol, pointer.run_id)).read_text()
        if hashlib.sha256(payload.encode()).hexdigest() != pointer.manifest_sha256:
            raise RuntimeError("Current manifest checksum does not match its pointer")
        return IngestionManifest.model_validate_json(payload)

    def publish_manifest(
        self, manifest: IngestionManifest, target: StorageTarget, expected_current_run_id: str | None
    ) -> Artifact:
        """Save a run snapshot then atomically advance the local current pointer."""
        manifest_key = self._manifest_key(
            target, manifest.quote_date.isoformat(), manifest.underlying_symbol, manifest.run_id
        )
        manifest_bytes = manifest.model_dump_json().encode()
        artifact = self._write_immutable(manifest_key, manifest_bytes, target, "application/json")
        pointer = ManifestPointer(
            quote_date=manifest.quote_date,
            underlying_symbol=manifest.underlying_symbol,
            run_id=manifest.run_id,
            manifest_uri=artifact.uri,
            manifest_sha256=artifact.sha256,
            published_at=manifest.published_at,
        )
        self._advance_pointer(
            self._path(target, self._pointer_key(target, manifest.quote_date.isoformat(), manifest.underlying_symbol)),
            pointer.model_dump_json().encode(),
            expected_current_run_id,
        )
        return artifact

    def _advance_pointer(self, path: Path, data: bytes, expected_run_id: str | None) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = path.with_suffix(".lock")
        acquired_lock = False
        try:
            with lock.open("x"):
                acquired_lock = True
                if path.is_file():
                    if ManifestPointer.model_validate_json(path.read_text()).run_id != expected_run_id:
                        raise RuntimeError("Current manifest changed before publication")
                elif expected_run_id is not None:
                    raise RuntimeError("Current manifest changed before publication")
                temporary = path.with_suffix(f"{path.suffix}.tmp")
                temporary.write_bytes(data)
                temporary.replace(path)
        except FileExistsError:
            raise RuntimeError("Current manifest is being published by another process") from None
        finally:
            if acquired_lock:
                lock.unlink(missing_ok=True)

    def _pointer_key(self, target: StorageTarget, quote_date: str, symbol: str) -> str:
        return FinancialDataS3Store._key(
            target,
            f"manifests/dataset=options.eod_quotes/schema_version=2.0/source=eodhd/quote_date={quote_date}/"
            f"underlying_symbol={symbol}/current.json",
        )

    def _manifest_key(self, target: StorageTarget, quote_date: str, symbol: str, run_id: str) -> str:
        return FinancialDataS3Store._key(
            target,
            f"manifests/dataset=options.eod_quotes/schema_version=2.0/source=eodhd/quote_date={quote_date}/"
            f"underlying_symbol={symbol}/runs/{run_id}.json",
        )

    def _path(self, target: StorageTarget, key: str) -> Path:
        path = (self.root / target.bucket / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Storage target resolves outside the local root")
        return path

    def _write_immutable(self, key: str, data: bytes, target: StorageTarget, content_type: str) -> Artifact:
        path = self._path(target, key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(data)
        return _artifact(path.as_uri(), key, content_type, data)


def _artifact(uri: str, key: str, content_type: str, data: bytes) -> Artifact:
    return Artifact(
        uri=uri,
        key=key,
        content_type=content_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        created_at=datetime.now(UTC),
    )
