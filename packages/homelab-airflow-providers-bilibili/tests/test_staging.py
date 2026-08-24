import hashlib
import sys
from pathlib import Path
from types import ModuleType

import pytest
from homelab_airflow_providers_bilibili.staging import ArtifactMaterializationError
from homelab_airflow_providers_bilibili.staging import S3ArtifactStager
from homelab_airflow_providers_bilibili.staging import S3RawResponseStore
from homelab_video_contracts import Artifact


def test_s3_stager_downloads_and_verifies(monkeypatch, tmp_path: Path) -> None:
    class FakeHook:
        def __init__(self, aws_conn_id):
            assert aws_conn_id == "rustfs_default"

        def download_file(self, *, key, bucket_name, local_path, **kwargs):
            assert key == "video/render.mp4"
            assert bucket_name == "bucket"
            downloaded = Path(local_path, "render.mp4")
            downloaded.write_bytes(b"video")
            return str(downloaded)

    module = ModuleType("airflow.providers.amazon.aws.hooks.s3")
    module.S3Hook = FakeHook
    monkeypatch.setitem(sys.modules, "airflow.providers.amazon.aws.hooks.s3", module)
    artifact = Artifact(
        uri="s3://bucket/video/render.mp4",
        content_type="video/mp4",
        size=5,
        sha256="0" * 64,
    )
    stager = S3ArtifactStager(root=tmp_path)
    with pytest.raises(ArtifactMaterializationError, match="sha256 mismatch"):
        stager.materialize(artifact, filename_hint="part-1.bin")


def test_s3_stager_rejects_unsafe_filename(tmp_path: Path) -> None:
    artifact = Artifact(uri="s3://bucket/video.mp4", content_type="video/mp4")
    stager = S3ArtifactStager(root=tmp_path)
    with pytest.raises(ArtifactMaterializationError, match="safe filename"):
        stager.materialize(artifact, filename_hint="../escape")


def test_s3_stager_uses_each_download_return_path_and_streams_hash(monkeypatch, tmp_path: Path) -> None:
    class FakeHook:
        calls = 0

        def __init__(self, aws_conn_id):
            assert aws_conn_id == "rustfs_default"

        def download_file(self, *, key, local_path, **kwargs):
            self.__class__.calls += 1
            downloaded = Path(local_path, f"generated-{self.calls}.tmp")
            downloaded.write_bytes(key.encode())
            return str(downloaded)

    module = ModuleType("airflow.providers.amazon.aws.hooks.s3")
    module.S3Hook = FakeHook
    monkeypatch.setitem(sys.modules, "airflow.providers.amazon.aws.hooks.s3", module)
    artifacts = [
        Artifact(
            uri=f"s3://bucket/{key}",
            content_type="video/mp4",
            size=len(key),
            sha256=hashlib.sha256(key.encode()).hexdigest(),
        )
        for key in ("part-one", "part-two")
    ]
    monkeypatch.setattr(Path, "read_bytes", lambda self: (_ for _ in ()).throw(AssertionError("not streaming")))
    stager = S3ArtifactStager(root=tmp_path)

    paths = [
        stager.materialize(artifact, filename_hint=f"part-{index}.mp4") for index, artifact in enumerate(artifacts)
    ]

    assert [path.name for path in paths] == ["generated-1.tmp", "generated-2.tmp"]


def test_raw_response_store_writes_json_to_rustfs(monkeypatch) -> None:
    captured = {}

    class FakeHook:
        def __init__(self, aws_conn_id):
            captured["conn_id"] = aws_conn_id

        def load_bytes(self, data, **kwargs):
            captured["data"] = data
            captured.update(kwargs)

    module = ModuleType("airflow.providers.amazon.aws.hooks.s3")
    module.S3Hook = FakeHook
    monkeypatch.setitem(sys.modules, "airflow.providers.amazon.aws.hooks.s3", module)

    uri = S3RawResponseStore().store({"code": 0, "data": {"aid": 1}}, uri="s3://audit/responses/1.json")

    assert uri == "s3://audit/responses/1.json"
    assert captured["conn_id"] == "rustfs_default"
    assert captured["bucket_name"] == "audit"
    assert captured["key"] == "responses/1.json"
    assert captured["replace"] is False
    assert b'"aid":1' in captured["data"]


def test_artifact_suffix_preserves_media_extension() -> None:
    from homelab_airflow_providers_bilibili.operators import _artifact_suffix

    artifact = Artifact(uri="s3://bucket/video/render.mp4", content_type="video/mp4")
    assert _artifact_suffix(artifact) == ".mp4"
