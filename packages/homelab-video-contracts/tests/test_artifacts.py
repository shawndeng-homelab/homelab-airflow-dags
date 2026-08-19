"""Tests for artifact and base contract validation."""

import pytest
from homelab_video_contracts.artifacts import Artifact
from pydantic import ValidationError


def test_artifact_round_trip_includes_schema_version(artifact: Artifact) -> None:
    """Persist and restore an artifact without losing version metadata."""
    payload = artifact.model_dump_json()
    restored = Artifact.model_validate_json(payload)

    assert restored == artifact
    assert restored.schema_version == "1.0"


@pytest.mark.parametrize(
    "uri",
    [
        "https://rustfs.example.com/bucket/key",
        "s3://bucket",
        "s3:///key",
        "s3://bucket/key?signature=secret",
    ],
)
def test_artifact_rejects_noncanonical_s3_uri(uri: str) -> None:
    """Reject HTTP, incomplete, and presigned artifact locations."""
    with pytest.raises(ValidationError, match="s3"):
        Artifact(uri=uri, content_type="video/mp4")


def test_artifact_rejects_unknown_fields() -> None:
    """Prevent silent schema drift in persisted JSON."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        Artifact(
            uri="s3://bucket/key",
            content_type="video/mp4",
            secret="must-not-pass",
        )


def test_artifact_rejects_invalid_sha256() -> None:
    """Require lowercase 64-character SHA-256 values."""
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        Artifact(uri="s3://bucket/key", content_type="video/mp4", sha256="ABC")
