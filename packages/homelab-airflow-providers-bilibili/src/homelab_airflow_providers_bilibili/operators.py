"""Airflow operators for Bilibili publish, lookup, and archive append."""

from __future__ import annotations

from collections.abc import Sequence
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
from homelab_video_contracts import BilibiliArchiveSnapshot
from homelab_video_contracts import BilibiliUploadRequest

from homelab_airflow_providers_bilibili.hooks import BilibiliHook
from homelab_airflow_providers_bilibili.staging import ArtifactStager
from homelab_airflow_providers_bilibili.staging import S3ArtifactStager


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


class BilibiliUploadOperator(BaseOperator):
    """Upload one complete archive through the biliup Python SDK."""

    template_fields = ("request", "local_parts", "cover_path")
    template_fields_renderers: ClassVar[dict[str, str]] = {"request": "json", "local_parts": "json"}

    def __init__(
        self,
        *,
        request: BilibiliUploadRequest | dict[str, Any],
        local_parts: list[str | Artifact] | tuple[str | Artifact, ...],
        cover_path: str | Artifact | None = None,
        rustfs_conn_id: str = "rustfs_default",
        bilibili_conn_id: str = BilibiliHook.default_conn_name,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.request = request
        self.local_parts = local_parts
        self.cover_path = cover_path
        self.rustfs_conn_id = rustfs_conn_id
        self.bilibili_conn_id = bilibili_conn_id

    def execute(self, context: Context) -> dict[str, Any]:
        request = (
            self.request
            if isinstance(self.request, BilibiliUploadRequest)
            else BilibiliUploadRequest.model_validate(self.request)
        )
        stager: S3ArtifactStager | None = None
        try:
            if any(isinstance(item, Artifact) for item in self.local_parts) or isinstance(self.cover_path, Artifact):
                stager = S3ArtifactStager(aws_conn_id=self.rustfs_conn_id)
            parts, stager = _materialize_parts(request.parts, self.local_parts, stager=stager)
            cover_source = self.cover_path if self.cover_path is not None else request.cover
            cover_path = None
            if isinstance(cover_source, Artifact):
                if stager is None:
                    stager = S3ArtifactStager(aws_conn_id=self.rustfs_conn_id)
                cover_path = stager.materialize(cover_source, filename_hint="cover.jpg")
            elif cover_source:
                cover_path = Path(cover_source)
            receipt = BilibiliHook(self.bilibili_conn_id).publish(request, parts, cover_path)
            self.log.info("Bilibili submission accepted: aid=%s bvid=%s", receipt.aid, receipt.bvid)
            return {
                "aid": receipt.aid,
                "bvid": receipt.bvid,
                "title": receipt.title,
                "status": receipt.status.value,
                "parts": [part.model_dump(mode="json") for part in receipt.parts],
                "raw_response": receipt.raw_response,
            }
        finally:
            if stager is not None:
                stager.cleanup()


class BilibiliAppendOperator(BaseOperator):
    """Append parts by preserving and editing the complete remote archive."""

    template_fields = ("archive", "request", "local_parts")
    template_fields_renderers: ClassVar[dict[str, str]] = {"archive": "json", "request": "json", "local_parts": "json"}

    def __init__(
        self,
        *,
        archive: BilibiliArchiveSnapshot | dict[str, Any],
        request: BilibiliAppendRequest | dict[str, Any],
        local_parts: list[str | Artifact] | tuple[str | Artifact, ...],
        rustfs_conn_id: str = "rustfs_default",
        bilibili_conn_id: str = BilibiliHook.default_conn_name,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.archive = archive
        self.request = request
        self.local_parts = local_parts
        self.rustfs_conn_id = rustfs_conn_id
        self.bilibili_conn_id = bilibili_conn_id

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
        if request.expected_part_count is not None and request.expected_part_count != len(archive.parts):
            raise AirflowException("Bilibili archive part count changed; refresh snapshot before appending")
        stager: S3ArtifactStager | None = None
        try:
            if any(isinstance(item, Artifact) for item in self.local_parts):
                stager = S3ArtifactStager(aws_conn_id=self.rustfs_conn_id)
            parts, stager = _materialize_parts(request.parts, self.local_parts, stager=stager)
            receipt = BilibiliHook(self.bilibili_conn_id).append(archive, request, parts)
            self.log.info("Bilibili archive edited: aid=%s bvid=%s", receipt.aid, receipt.bvid)
            return {
                "aid": receipt.aid,
                "bvid": receipt.bvid,
                "title": receipt.title,
                "status": receipt.status.value,
                "parts": [part.model_dump(mode="json") for part in receipt.parts],
                "raw_response": receipt.raw_response,
            }
        finally:
            if stager is not None:
                stager.cleanup()


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
