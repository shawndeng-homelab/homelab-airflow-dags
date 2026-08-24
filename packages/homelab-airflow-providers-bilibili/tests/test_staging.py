import sys
from pathlib import Path
from types import ModuleType

import pytest
from homelab_airflow_providers_bilibili.staging import ArtifactMaterializationError
from homelab_airflow_providers_bilibili.staging import S3ArtifactStager
from homelab_video_contracts import Artifact


def test_s3_stager_downloads_and_verifies(monkeypatch, tmp_path: Path) -> None:
    class FakeHook:
        def __init__(self, aws_conn_id):
            assert aws_conn_id == "rustfs_default"

        def download_file(self, *, key, bucket_name, local_path, **kwargs):
            assert key == "video/render.mp4"
            assert bucket_name == "bucket"
            Path(local_path, "render.mp4").write_bytes(b"video")

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


def test_artifact_suffix_preserves_media_extension() -> None:
    from homelab_airflow_providers_bilibili.operators import _artifact_suffix

    artifact = Artifact(uri="s3://bucket/video/render.mp4", content_type="video/mp4")
    assert _artifact_suffix(artifact) == ".mp4"
