import hashlib
from pathlib import Path

import pytest
from airflow.exceptions import AirflowException
from homelab_airflow_providers_bilibili.client import BilibiliSubmissionReceipt
from homelab_airflow_providers_bilibili.operators import BilibiliAppendOperator
from homelab_airflow_providers_bilibili.operators import BilibiliUploadOperator
from homelab_video_contracts import Artifact
from homelab_video_contracts import BilibiliAppendRequest
from homelab_video_contracts import BilibiliArchivePart
from homelab_video_contracts import BilibiliArchiveSnapshot
from homelab_video_contracts import BilibiliPartInput
from homelab_video_contracts import BilibiliPartResult
from homelab_video_contracts import BilibiliPublicationRecord
from homelab_video_contracts import BilibiliPublicationStatus
from homelab_video_contracts import BilibiliUploadRequest


class MemoryRegistry:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str], BilibiliPublicationRecord] = {}

    @staticmethod
    def _key(*, source_video_id, account_id, request_sha256):
        return source_video_id, account_id, request_sha256

    def get(self, **key):
        return self.records.get(self._key(**key))

    def upsert(self, record):
        self.records[(record.source_video_id, record.account_id, record.request_sha256)] = record
        return record

    def claim(self, record):
        key = (record.source_video_id, record.account_id, record.request_sha256)
        if key in self.records:
            return False
        self.records[key] = record
        return True


class FakeHook:
    publish_calls = 0
    append_calls = 0

    def __init__(self, conn_id):
        self.conn_id = conn_id

    def get_account_id(self):
        return "main"

    def publish(self, request, parts, cover_path):
        self.__class__.publish_calls += 1
        result = BilibiliPartResult(
            index=1,
            title=request.parts[0].title,
            source_sha256=request.parts[0].video.sha256,
            remote_filename="remote-new",
        )
        return BilibiliSubmissionReceipt(
            aid=7,
            bvid="BVNEW",
            title=request.title,
            status=BilibiliPublicationStatus.SUBMITTED,
            parts=(result,),
            raw_response={"code": 0, "data": {"aid": 7, "bvid": "BVNEW"}},
        )

    def append(self, archive, request, parts):
        self.__class__.append_calls += 1
        result = BilibiliPartResult(
            index=len(archive.parts) + 1,
            title=request.parts[0].title,
            source_sha256=request.parts[0].video.sha256,
            remote_filename="remote-appended",
        )
        return BilibiliSubmissionReceipt(
            aid=archive.aid,
            bvid=archive.bvid,
            title=archive.title,
            status=BilibiliPublicationStatus.SUBMITTED,
            parts=(*archive.parts, result),
            raw_response={"code": 0, "data": {"aid": archive.aid}},
        )


def _part(path: Path, title: str = "P1") -> BilibiliPartInput:
    content = path.read_bytes()
    return BilibiliPartInput(
        video=Artifact(
            uri=f"s3://bucket/{path.name}",
            content_type="video/mp4",
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        ),
        title=title,
    )


def test_upload_registry_reuses_result_and_excludes_raw_response(monkeypatch, tmp_path: Path) -> None:
    from homelab_airflow_providers_bilibili import operators

    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")
    request = BilibiliUploadRequest(source_video_id="yt-1", title="title", parts=(_part(media),))
    registry = MemoryRegistry()
    FakeHook.publish_calls = 0
    monkeypatch.setattr(operators, "BilibiliHook", FakeHook)
    stored = {}

    class FakeStore:
        def __init__(self, aws_conn_id):
            stored["conn_id"] = aws_conn_id

        def store(self, payload, *, uri):
            stored["payload"] = payload
            return uri

    monkeypatch.setattr(operators, "S3RawResponseStore", FakeStore)
    operator = BilibiliUploadOperator(
        task_id="upload",
        request=request,
        local_parts=[str(media)],
        raw_response_uri="s3://audit/upload.json",
        publication_registry=registry,
    )

    first = operator.execute({})
    second = operator.execute({})

    assert FakeHook.publish_calls == 1
    assert first["raw_response_uri"] == "s3://audit/upload.json"
    assert "raw_response" not in first
    assert stored["payload"]["data"]["aid"] == 7
    assert second["idempotent_reuse"] is True
    assert second["aid"] == 7


def test_upload_defaults_local_parts_from_request_artifacts(monkeypatch, tmp_path: Path) -> None:
    from homelab_airflow_providers_bilibili import operators

    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")
    request = BilibiliUploadRequest(source_video_id="yt-2", title="title", parts=(_part(media),))
    materialized = []

    class FakeStager:
        def __init__(self, aws_conn_id):
            pass

        def materialize(self, artifact, *, filename_hint):
            materialized.append((artifact, filename_hint))
            return media

        def cleanup(self):
            pass

    FakeHook.publish_calls = 0
    monkeypatch.setattr(operators, "BilibiliHook", FakeHook)
    monkeypatch.setattr(operators, "S3ArtifactStager", FakeStager)
    BilibiliUploadOperator(
        task_id="upload_default_parts",
        request=request,
        publication_registry=MemoryRegistry(),
    ).execute({})

    assert FakeHook.publish_calls == 1
    assert materialized[0][0] == request.parts[0].video
    assert materialized[0][1].endswith(".mp4")


def test_unknown_registry_record_fails_closed(monkeypatch, tmp_path: Path) -> None:
    from homelab_airflow_providers_bilibili import operators
    from homelab_airflow_providers_bilibili.client import request_digest

    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")
    request = BilibiliUploadRequest(source_video_id="yt-3", title="title", parts=(_part(media),))
    registry = MemoryRegistry()
    registry.upsert(
        BilibiliPublicationRecord(
            source_video_id="yt-3",
            account_id="main",
            request_sha256=request_digest(request),
            status=BilibiliPublicationStatus.UNKNOWN,
        )
    )
    FakeHook.publish_calls = 0
    monkeypatch.setattr(operators, "BilibiliHook", FakeHook)

    with pytest.raises(AirflowException, match="reconcile before retrying"):
        BilibiliUploadOperator(
            task_id="upload_fail_closed",
            request=request,
            local_parts=[str(media)],
            publication_registry=registry,
        ).execute({})

    assert FakeHook.publish_calls == 0


def test_append_registry_reuses_new_parts_without_duplicate_edit(monkeypatch, tmp_path: Path) -> None:
    from homelab_airflow_providers_bilibili import operators

    media = tmp_path / "new.mp4"
    media.write_bytes(b"new")
    part = _part(media, "P2")
    archive = BilibiliArchiveSnapshot(
        aid=9,
        bvid="BVOLD",
        title="archive",
        parts=(BilibiliArchivePart(index=1, title="P1", remote_filename="old"),),
        archive={"aid": 9, "bvid": "BVOLD", "title": "archive"},
        videos=({"filename": "old", "title": "P1", "desc": ""},),
    )
    request = BilibiliAppendRequest(aid=9, bvid="BVOLD", expected_part_count=1, parts=(part,))
    registry = MemoryRegistry()
    FakeHook.append_calls = 0
    monkeypatch.setattr(operators, "BilibiliHook", FakeHook)
    operator = BilibiliAppendOperator(
        task_id="append",
        archive=archive,
        request=request,
        local_parts=[str(media)],
        publication_registry=registry,
    )

    first = operator.execute({})
    second = operator.execute({})

    assert FakeHook.append_calls == 1
    assert len(first["parts"]) == 2
    assert len(second["parts"]) == 2
    assert second["idempotent_reuse"] is True


def test_cleanup_failure_does_not_replace_original_error() -> None:
    from homelab_airflow_providers_bilibili.operators import _cleanup_stager

    class BrokenStager:
        def cleanup(self):
            raise OSError("cleanup")

    class FakeLog:
        def warning(self, *args, **kwargs):
            pass

    with pytest.raises(ValueError, match="original"):
        try:
            raise ValueError("original")
        finally:
            _cleanup_stager(BrokenStager(), FakeLog())
