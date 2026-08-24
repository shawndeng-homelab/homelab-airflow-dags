"""Airflow operators for Bilibili publish, lookup, and archive append."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from datetime import UTC
from datetime import datetime
from mimetypes import guess_extension
from pathlib import Path
from typing import Any
from typing import ClassVar
from urllib.parse import urlsplit

from airflow.exceptions import AirflowException
from airflow.models import BaseOperator
from airflow.utils.context import Context
from homelab_video_contracts import Artifact
from homelab_video_contracts import BilibiliAppendRequest
from homelab_video_contracts import BilibiliArchivePart
from homelab_video_contracts import BilibiliArchiveSnapshot
from homelab_video_contracts import BilibiliPartResult
from homelab_video_contracts import BilibiliPublicationRecord
from homelab_video_contracts import BilibiliPublicationStatus
from homelab_video_contracts import BilibiliUploadRequest

from homelab_airflow_providers_bilibili.client import request_digest
from homelab_airflow_providers_bilibili.hooks import BilibiliHook
from homelab_airflow_providers_bilibili.registry import AirflowVariablePublicationRegistry
from homelab_airflow_providers_bilibili.registry import BilibiliPublicationRegistry
from homelab_airflow_providers_bilibili.staging import ArtifactStager
from homelab_airflow_providers_bilibili.staging import S3ArtifactStager
from homelab_airflow_providers_bilibili.staging import S3RawResponseStore


def _artifact_suffix(artifact: Artifact) -> str:
    """Choose a safe media extension for biliup probing."""
    suffix = Path(urlsplit(artifact.uri).path).suffix.lower()
    if suffix and suffix.isascii() and suffix[1:].isalnum() and len(suffix) <= 8:
        return suffix
    return guess_extension(artifact.content_type, strict=False) or ".bin"


def _materialize_parts(
    artifacts: Sequence[Any],
    local_parts: Sequence[str | Artifact],
    *,
    stager: ArtifactStager | None,
) -> tuple[list[Path], ArtifactStager | None]:
    if len(local_parts) != len(artifacts):
        raise AirflowException("local_parts must have the same length as request parts")
    resolved_stager = stager
    paths: list[Path] = []
    for index, source in enumerate(local_parts, start=1):
        if isinstance(source, Artifact):
            if resolved_stager is None:
                resolved_stager = S3ArtifactStager()
            paths.append(resolved_stager.materialize(source, filename_hint=f"part-{index}{_artifact_suffix(source)}"))
        else:
            paths.append(Path(source))
    return paths, resolved_stager


def _record_output(
    record: BilibiliPublicationRecord,
    *,
    parts: Sequence[BilibiliPartResult | BilibiliArchivePart] | None = None,
) -> dict[str, Any]:
    if record.aid is None or record.bvid is None:
        raise AirflowException("Bilibili publication is claimed but has no reusable remote identity")
    output_parts = parts if parts is not None else record.parts
    return {
        "aid": record.aid,
        "bvid": record.bvid,
        "status": record.status.value,
        "parts": [part.model_dump(mode="json") for part in output_parts],
        "raw_response_uri": record.raw_response_uri,
        "idempotent_reuse": True,
    }


def _reuse_record(
    record: BilibiliPublicationRecord | None,
    *,
    parts: Sequence[BilibiliPartResult | BilibiliArchivePart] | None = None,
) -> dict[str, Any] | None:
    if record is None:
        return None
    if record.status in {
        BilibiliPublicationStatus.SUBMITTED,
        BilibiliPublicationStatus.REVIEWING,
        BilibiliPublicationStatus.PUBLISHED,
    }:
        return _record_output(record, parts=parts)
    raise AirflowException(
        "Bilibili publication key is already claimed without a safely reusable result; reconcile before retrying"
    )


def _merge_append_parts(
    archive_parts: Sequence[BilibiliArchivePart],
    recorded_parts: Sequence[BilibiliPartResult],
) -> tuple[BilibiliArchivePart | BilibiliPartResult, ...]:
    filenames = {part.remote_filename for part in archive_parts}
    return (*archive_parts, *(part for part in recorded_parts if part.remote_filename not in filenames))


def _cleanup_stager(stager: ArtifactStager | None, log: Any) -> None:
    if stager is None:
        return
    active_error = sys.exception()
    try:
        stager.cleanup()
    except Exception:
        if active_error is None:
            raise
        log.warning("Bilibili artifact cleanup failed after another exception", exc_info=True)


class BilibiliUploadOperator(BaseOperator):
    """Upload one complete archive through the biliup Python SDK."""

    template_fields = ("request", "local_parts", "cover_path", "raw_response_uri")
    template_fields_renderers: ClassVar[dict[str, str]] = {"request": "json", "local_parts": "json"}

    def __init__(
        self,
        *,
        request: BilibiliUploadRequest | dict[str, Any],
        local_parts: list[str | Artifact] | tuple[str | Artifact, ...] | None = None,
        cover_path: str | Artifact | None = None,
        raw_response_uri: str | None = None,
        rustfs_conn_id: str = "rustfs_default",
        bilibili_conn_id: str = BilibiliHook.default_conn_name,
        publication_registry: BilibiliPublicationRegistry | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.request = request
        self.local_parts = local_parts
        self.cover_path = cover_path
        self.raw_response_uri = raw_response_uri
        self.rustfs_conn_id = rustfs_conn_id
        self.bilibili_conn_id = bilibili_conn_id
        self.publication_registry = publication_registry

    def execute(self, context: Context) -> dict[str, Any]:
        request = (
            self.request
            if isinstance(self.request, BilibiliUploadRequest)
            else BilibiliUploadRequest.model_validate(self.request)
        )
        hook = BilibiliHook(self.bilibili_conn_id)
        account_id = hook.get_account_id()
        digest = request_digest(request)
        registry = self.publication_registry or AirflowVariablePublicationRegistry()
        registry_key = {
            "source_video_id": request.source_video_id,
            "account_id": account_id,
            "request_sha256": digest,
        }
        reused = _reuse_record(registry.get(**registry_key))
        if reused is not None:
            reused["title"] = request.title
            return reused
        local_sources = self.local_parts if self.local_parts is not None else [part.video for part in request.parts]
        stager: S3ArtifactStager | None = None
        try:
            if any(isinstance(item, Artifact) for item in local_sources) or isinstance(self.cover_path, Artifact):
                stager = S3ArtifactStager(aws_conn_id=self.rustfs_conn_id)
            parts, stager = _materialize_parts(request.parts, local_sources, stager=stager)
            cover_source = self.cover_path if self.cover_path is not None else request.cover
            cover_path = None
            if isinstance(cover_source, Artifact):
                if stager is None:
                    stager = S3ArtifactStager(aws_conn_id=self.rustfs_conn_id)
                cover_path = stager.materialize(cover_source, filename_hint="cover.jpg")
            elif cover_source:
                cover_path = Path(cover_source)
            reservation = BilibiliPublicationRecord(**registry_key, status=BilibiliPublicationStatus.UNKNOWN)
            if not registry.claim(reservation):
                reused = _reuse_record(registry.get(**registry_key))
                if reused is None:
                    raise AirflowException("Bilibili publication claim disappeared; fail closed")
                reused["title"] = request.title
                return reused
            receipt = hook.publish(request, parts, cover_path)
            raw_response_uri = None
            if self.raw_response_uri is not None:
                raw_response_uri = S3RawResponseStore(aws_conn_id=self.rustfs_conn_id).store(
                    receipt.raw_response,
                    uri=self.raw_response_uri,
                )
            submitted_at = datetime.now(UTC)
            result_parts = tuple(part for part in receipt.parts if isinstance(part, BilibiliPartResult))
            registry.upsert(
                BilibiliPublicationRecord(
                    **registry_key,
                    status=BilibiliPublicationStatus(receipt.status),
                    aid=receipt.aid,
                    bvid=receipt.bvid,
                    first_submitted_at=submitted_at,
                    last_checked_at=submitted_at,
                    parts=result_parts,
                    raw_response_uri=raw_response_uri,
                )
            )
            self.log.info("Bilibili submission accepted: aid=%s bvid=%s", receipt.aid, receipt.bvid)
            return {
                "aid": receipt.aid,
                "bvid": receipt.bvid,
                "title": receipt.title,
                "status": receipt.status.value,
                "parts": [part.model_dump(mode="json") for part in receipt.parts],
                "raw_response_uri": raw_response_uri,
                "idempotent_reuse": False,
            }
        finally:
            _cleanup_stager(stager, self.log)


class BilibiliAppendOperator(BaseOperator):
    """Append parts by preserving and editing the complete remote archive."""

    template_fields = ("archive", "request", "local_parts", "raw_response_uri")
    template_fields_renderers: ClassVar[dict[str, str]] = {"archive": "json", "request": "json", "local_parts": "json"}

    def __init__(
        self,
        *,
        archive: BilibiliArchiveSnapshot | dict[str, Any],
        request: BilibiliAppendRequest | dict[str, Any],
        local_parts: list[str | Artifact] | tuple[str | Artifact, ...] | None = None,
        raw_response_uri: str | None = None,
        rustfs_conn_id: str = "rustfs_default",
        bilibili_conn_id: str = BilibiliHook.default_conn_name,
        publication_registry: BilibiliPublicationRegistry | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.archive = archive
        self.request = request
        self.local_parts = local_parts
        self.raw_response_uri = raw_response_uri
        self.rustfs_conn_id = rustfs_conn_id
        self.bilibili_conn_id = bilibili_conn_id
        self.publication_registry = publication_registry

    def execute(self, context: Context) -> dict[str, Any]:
        archive = (
            self.archive
            if isinstance(self.archive, BilibiliArchiveSnapshot)
            else BilibiliArchiveSnapshot.model_validate(self.archive)
        )
        request = (
            self.request
            if isinstance(self.request, BilibiliAppendRequest)
            else BilibiliAppendRequest.model_validate(self.request)
        )
        if request.aid is not None and request.aid != archive.aid:
            raise AirflowException("append request aid does not match archive")
        if request.bvid is not None and request.bvid != archive.bvid:
            raise AirflowException("append request bvid does not match archive")
        hook = BilibiliHook(self.bilibili_conn_id)
        account_id = hook.get_account_id()
        digest = request_digest(request)
        registry = self.publication_registry or AirflowVariablePublicationRegistry()
        registry_key = {
            "source_video_id": f"bilibili:{archive.aid}",
            "account_id": account_id,
            "request_sha256": digest,
        }
        existing = registry.get(**registry_key)
        reused = _reuse_record(
            existing,
            parts=_merge_append_parts(archive.parts, existing.parts) if existing is not None else None,
        )
        if reused is not None:
            reused["title"] = archive.title
            return reused
        if not archive.archive or not archive.videos or len(archive.videos) != len(archive.parts):
            raise AirflowException("append requires complete creative-center archive and videos data")
        if request.expected_part_count is not None and request.expected_part_count != len(archive.videos):
            raise AirflowException("Bilibili archive part count changed; refresh snapshot before appending")
        local_sources = self.local_parts if self.local_parts is not None else [part.video for part in request.parts]
        stager: S3ArtifactStager | None = None
        try:
            if any(isinstance(item, Artifact) for item in local_sources):
                stager = S3ArtifactStager(aws_conn_id=self.rustfs_conn_id)
            parts, stager = _materialize_parts(request.parts, local_sources, stager=stager)
            reservation = BilibiliPublicationRecord(**registry_key, status=BilibiliPublicationStatus.UNKNOWN)
            if not registry.claim(reservation):
                record = registry.get(**registry_key)
                reused = _reuse_record(
                    record,
                    parts=_merge_append_parts(archive.parts, record.parts) if record is not None else None,
                )
                if reused is None:
                    raise AirflowException("Bilibili append claim disappeared; fail closed")
                reused["title"] = archive.title
                return reused
            receipt = hook.append(archive, request, parts)
            raw_response_uri = None
            if self.raw_response_uri is not None:
                raw_response_uri = S3RawResponseStore(aws_conn_id=self.rustfs_conn_id).store(
                    receipt.raw_response,
                    uri=self.raw_response_uri,
                )
            submitted_at = datetime.now(UTC)
            new_parts = tuple(part for part in receipt.parts if isinstance(part, BilibiliPartResult))
            registry.upsert(
                BilibiliPublicationRecord(
                    **registry_key,
                    status=BilibiliPublicationStatus(receipt.status),
                    aid=receipt.aid,
                    bvid=receipt.bvid,
                    first_submitted_at=submitted_at,
                    last_checked_at=submitted_at,
                    parts=new_parts,
                    raw_response_uri=raw_response_uri,
                )
            )
            self.log.info("Bilibili archive edited: aid=%s bvid=%s", receipt.aid, receipt.bvid)
            return {
                "aid": receipt.aid,
                "bvid": receipt.bvid,
                "title": receipt.title,
                "status": receipt.status.value,
                "parts": [part.model_dump(mode="json") for part in receipt.parts],
                "raw_response_uri": raw_response_uri,
                "idempotent_reuse": False,
            }
        finally:
            _cleanup_stager(stager, self.log)


class BilibiliArchiveLookupOperator(BaseOperator):
    """Fetch a normalized remote archive snapshot for reconcile or append."""

    template_fields = ("aid",)

    def __init__(
        self,
        *,
        aid: int,
        bilibili_conn_id: str = BilibiliHook.default_conn_name,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.aid = aid
        self.bilibili_conn_id = bilibili_conn_id

    def execute(self, context: Context) -> dict[str, Any]:
        snapshot = BilibiliHook(self.bilibili_conn_id).get_archive(int(self.aid))
        self.log.info(
            "Bilibili archive fetched: aid=%s bvid=%s status=%s parts=%s",
            snapshot.aid,
            snapshot.bvid,
            snapshot.status.value,
            len(snapshot.parts),
        )
        return snapshot.model_dump(mode="json")
