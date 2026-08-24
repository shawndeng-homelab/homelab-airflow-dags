from pathlib import Path

import pytest
from homelab_airflow_providers_bilibili.client import BilibiliLoginStatus
from homelab_airflow_providers_bilibili.client import BilibiliSubmissionReceipt
from homelab_airflow_providers_bilibili.client import BilibiliTransientError
from homelab_airflow_providers_bilibili.client import request_digest
from homelab_airflow_providers_bilibili.hooks import BilibiliHook
from homelab_video_contracts import Artifact
from homelab_video_contracts import BilibiliArchivePart
from homelab_video_contracts import BilibiliArchiveSnapshot
from homelab_video_contracts import BilibiliPartInput
from homelab_video_contracts import BilibiliUploadRequest


def _request() -> BilibiliUploadRequest:
    return BilibiliUploadRequest(
        source_video_id="yt-1",
        title="localized title",
        parts=(
            BilibiliPartInput(
                video=Artifact(uri="s3://bucket/render.mp4", content_type="video/mp4", sha256="a" * 64),
                title="P1",
            ),
        ),
    )


class FakeClient:
    def check_login(self) -> BilibiliLoginStatus:
        return BilibiliLoginStatus(ok=True, account_id="42", message="ok")

    def get_archive(self, aid):
        return BilibiliArchiveSnapshot(aid=aid, bvid="BV1", title="localized title")

    def publish(self, request, local_parts, cover_path=None):
        assert request.title == "localized title"
        assert local_parts == [Path("render.mp4")]
        return BilibiliSubmissionReceipt(1, "BV1", request.title, "submitted", (), {"code": 0})

    def append(self, archive, request, local_parts):
        return BilibiliSubmissionReceipt(
            archive.aid, archive.bvid, request.title, "submitted", archive.parts, {"code": 0}
        )


def test_request_digest_is_stable() -> None:
    assert request_digest(_request()) == request_digest(_request())


def test_hook_delegates_without_exposing_credentials() -> None:
    hook = BilibiliHook(client=FakeClient())
    assert hook.test_connection() == (True, "ok")
    receipt = hook.publish(_request(), [Path("render.mp4")])
    assert receipt.aid == 1


def test_hook_fetches_archive_snapshot() -> None:
    archive = BilibiliHook(client=FakeClient()).get_archive(7)
    assert archive.aid == 7
    assert archive.status.value == "unknown"


def test_hook_maps_client_error_to_airflow_exception() -> None:
    class BrokenClient(FakeClient):
        def publish(self, request, local_parts, cover_path=None):
            raise BilibiliTransientError("rate limited")

    with pytest.raises(Exception, match="rate limited"):
        BilibiliHook(client=BrokenClient()).publish(_request(), [Path("render.mp4")])


def test_archive_snapshot_keeps_remote_part_identity() -> None:
    part = BilibiliArchivePart(index=1, title="P1", remote_filename="remote-1")
    archive = BilibiliArchiveSnapshot(aid=1, bvid="BV1", title="old", parts=(part,))
    assert archive.parts[0].remote_filename == "remote-1"


def test_sdk_adapter_normalizes_remote_archive(monkeypatch) -> None:
    from homelab_airflow_providers_bilibili.client import BiliupSdkAdapter

    class FakeBili:
        def __init__(self, data):
            self.data = data

        def get_video_info(self, aid):
            assert aid == 9
            return {
                "aid": 9,
                "bvid": "BV9",
                "title": "remote",
                "desc": "description",
                "tid": 171,
                "tag": "one,two",
                "pic": "https://img.example/cover.jpg",
                "copyright": 1,
                "state": 0,
                "pages": [{"part": "P1", "cid": 99, "filename": "remote.mp4"}],
            }

    class FakeModule:
        Data = dict
        BiliBili = FakeBili

    adapter = BiliupSdkAdapter(Path("unused"))
    monkeypatch.setattr(adapter, "_modules", lambda: (FakeModule, object()))
    monkeypatch.setattr(adapter, "_login", lambda bili: None)
    snapshot = adapter.get_archive(9)
    assert snapshot.status.value == "published"
    assert snapshot.parts[0].cid == 99
    assert snapshot.parts[0].remote_filename == "remote.mp4"


def test_publication_record_has_stable_registry_key() -> None:
    from homelab_airflow_providers_bilibili.registry import publication_key
    from homelab_video_contracts import BilibiliPublicationRecord

    record = BilibiliPublicationRecord(
        source_video_id="yt-1",
        account_id="main",
        request_sha256="a" * 64,
        aid=1,
        bvid="BV1",
    )
    assert publication_key(record) == ("yt-1", "main", "a" * 64)
