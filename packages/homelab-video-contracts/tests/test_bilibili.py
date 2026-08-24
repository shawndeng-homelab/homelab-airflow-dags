import pytest
from homelab_video_contracts import Artifact
from homelab_video_contracts import BilibiliAppendRequest
from homelab_video_contracts import BilibiliPartInput
from pydantic import ValidationError


def _part() -> BilibiliPartInput:
    return BilibiliPartInput(
        video=Artifact(uri="s3://bucket/video.mp4", content_type="video/mp4", sha256="a" * 64),
        title="P1",
    )


def test_append_request_requires_valid_target() -> None:
    """Append targets must use a positive aid or a BV identifier."""
    with pytest.raises(ValidationError, match="aid or bvid"):
        BilibiliAppendRequest(parts=(_part(),))
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        BilibiliAppendRequest(bvid="av123", parts=(_part(),))


def test_append_request_rejects_removed_tid_and_tags_fields() -> None:
    """Append metadata comes from the archive rather than request overrides."""
    with pytest.raises(ValidationError, match="extra_forbidden"):
        BilibiliAppendRequest.model_validate(
            {"aid": 1, "parts": [_part().model_dump(mode="json")], "tid": 171, "tags": ["wrong"]}
        )


def test_append_expected_part_count_is_non_negative() -> None:
    """The optimistic part-count guard cannot be negative."""
    with pytest.raises(ValidationError, match="greater_than_equal"):
        BilibiliAppendRequest(aid=1, expected_part_count=-1, parts=(_part(),))
