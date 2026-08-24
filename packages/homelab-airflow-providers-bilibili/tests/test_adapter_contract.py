import hashlib
import json
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import ClassVar

import pytest
from homelab_airflow_providers_bilibili.client import BilibiliInputError
from homelab_airflow_providers_bilibili.client import BiliupSdkAdapter
from homelab_video_contracts import Artifact
from homelab_video_contracts import BilibiliAppendRequest
from homelab_video_contracts import BilibiliArchivePart
from homelab_video_contracts import BilibiliArchiveSnapshot
from homelab_video_contracts import BilibiliPartInput
from homelab_video_contracts import BilibiliPublishSettings
from homelab_video_contracts import BilibiliUploadRequest


@dataclass
class FakeData:
    copyright: int = 2
    source: str = ""
    tid: int = 21
    cover: str = ""
    title: str = ""
    desc_format_id: int = 0
    desc: str = ""
    desc_v2: list = field(default_factory=list)
    dynamic: str = ""
    subtitle: dict = field(init=False)
    tag: str = ""
    videos: list = field(default_factory=list)
    dtime: int | None = None
    dolby: int = 0
    hires: int = 0
    no_reprint: int = 0
    is_only_self: int = 0
    charging_pay: int = 0
    extra_fields: str = ""
    aid: int | None = None

    def __post_init__(self) -> None:
        """Create the SDK-computed subtitle payload."""
        self.subtitle = {"open": 0, "lan": ""}

    def append(self, video: dict) -> None:
        self.videos.append(video)


class FakeSession:
    def __init__(self) -> None:
        self.proxies: dict[str, str] = {}


class FakeBili:
    instances: ClassVar[list["FakeBili"]] = []
    submissions: ClassVar[list[tuple[str, bool, dict]]] = []

    def __init__(self, video: FakeData) -> None:
        self.video = video
        self._BiliBili__session = FakeSession()
        self.instances.append(self)

    def upload_file(self, path: str) -> dict:
        return {"filename": f"remote-{Path(path).stem}", "upload_id": "upload-1"}

    def submit(self, submit_api: str, edit: bool = False, videos: FakeData | None = None) -> dict:
        payload = asdict(videos)
        extra_fields = json.loads(payload.pop("extra_fields") or "{}")
        for key, value in extra_fields.items():
            payload.setdefault(key, value)
        self.submissions.append((submit_api, edit, payload))
        data = {"aid": videos.aid or 7}
        if not edit:
            data["bvid"] = "BVNEW"
        return {"code": 0, "data": data}


class FakeModule:
    Data = FakeData
    BiliBili = FakeBili


def _part(path: Path, *, title: str = "P1", description: str = "part description") -> BilibiliPartInput:
    content = path.read_bytes()
    return BilibiliPartInput(
        video=Artifact(
            uri=f"s3://bucket/{path.name}",
            content_type="video/mp4",
            size=len(content),
            sha256=hashlib.sha256(content).hexdigest(),
        ),
        title=title,
        description=description,
    )


def _adapter(*, submit_api: str = "web", proxy: str | None = None) -> BiliupSdkAdapter:
    FakeBili.instances = []
    FakeBili.submissions = []
    adapter = BiliupSdkAdapter(Path("unused"), submit_api=submit_api, proxy=proxy)
    adapter._modules = lambda: (FakeModule, FakeModule)
    adapter._login = lambda bili: None
    return adapter


def test_publish_uses_sync_sdk_payload_and_client_settings(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")
    settings = BilibiliPublishSettings(
        dolby=True,
        lossless_music=True,
        no_reprint=True,
        charging_pay=True,
        close_reply=True,
        selection_reply=True,
        close_danmu=True,
        extra_fields={"topic_id": 42},
    )
    request = BilibiliUploadRequest(
        source_video_id="yt-1",
        parts=(_part(media),),
        title="title",
        tid=171,
        tags=("one", "two"),
        settings=settings,
    )
    adapter = _adapter(submit_api="client", proxy="http://proxy.example:8080")

    receipt = adapter.publish(request, [media])

    assert receipt.bvid == "BVNEW"
    submit_api, edit, payload = FakeBili.submissions[-1]
    assert (submit_api, edit) == ("client", False)
    assert payload["tag"] == "one,two"
    assert payload["dolby"] == payload["hires"] == payload["no_reprint"] == 1
    assert payload["charging_pay"] == 1
    assert payload["topic_id"] == 42
    assert payload["up_close_reply"] is True
    assert payload["up_selection_reply"] is True
    assert payload["up_close_danmu"] is True
    assert all(
        instance._BiliBili__session.proxies["https"] == "http://proxy.example:8080" for instance in FakeBili.instances
    )


def test_publish_honors_web_submit_and_supported_settings(tmp_path: Path) -> None:
    media = tmp_path / "web.mp4"
    media.write_bytes(b"web-video")
    request = BilibiliUploadRequest(
        source_video_id="yt-web",
        parts=(_part(media),),
        title="web title",
        settings=BilibiliPublishSettings(dolby=True, no_reprint=True),
    )

    _adapter(submit_api="web").publish(request, [media])

    submit_api, edit, payload = FakeBili.submissions[-1]
    assert (submit_api, edit) == ("web", False)
    assert payload["dolby"] == 1
    assert payload["no_reprint"] == 1


def test_web_submit_rejects_client_only_and_reserved_settings(tmp_path: Path) -> None:
    media = tmp_path / "video.mp4"
    media.write_bytes(b"video")
    adapter = _adapter()
    request = BilibiliUploadRequest(
        source_video_id="yt-1",
        parts=(_part(media),),
        title="title",
        settings=BilibiliPublishSettings(close_reply=True),
    )
    with pytest.raises(BilibiliInputError, match="require submit_api=client"):
        adapter.publish(request, [media])

    reserved = request.model_copy(update={"settings": BilibiliPublishSettings(extra_fields={"title": "override"})})
    with pytest.raises(BilibiliInputError, match="cannot override"):
        adapter.publish(reserved, [media])


def test_append_preserves_complete_creative_center_payload(tmp_path: Path) -> None:
    media = tmp_path / "new.mp4"
    media.write_bytes(b"new-video")
    old_video = {
        "filename": "old-filename",
        "title": "Old P1",
        "desc": "old part description",
        "cid": 99,
        "archive": {"keep": True},
    }
    archive_payload = {
        "aid": 9,
        "bvid": "BVOLD",
        "title": "archive title",
        "desc": "archive description",
        "tid": 171,
        "tag": "one,two",
        "copyright": 1,
        "cover": "//cover",
        "dynamic": "dynamic",
        "topic_id": 88,
    }
    archive = BilibiliArchiveSnapshot(
        aid=9,
        bvid="BVOLD",
        title="archive title",
        description="archive description",
        tid=171,
        tags=("one", "two"),
        parts=(
            BilibiliArchivePart(
                index=1,
                title="Old P1",
                description="old part description",
                remote_filename="old-filename",
                cid=99,
            ),
        ),
        archive=archive_payload,
        videos=(old_video,),
    )
    request = BilibiliAppendRequest(
        aid=9,
        bvid="BVOLD",
        expected_part_count=1,
        parts=(_part(media, title="New P2", description="new part description"),),
    )
    adapter = _adapter()

    receipt = adapter.append(archive, request, [media])

    assert receipt.bvid == "BVOLD"
    submit_api, edit, payload = FakeBili.submissions[-1]
    assert (submit_api, edit) == ("web", True)
    assert payload["topic_id"] == 88
    assert payload["videos"][0] == old_video
    assert payload["videos"][1]["filename"] == "remote-new"
    assert payload["videos"][1]["desc"] == "new part description"


def test_append_validates_target_count_and_local_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.mp4"
    part = BilibiliPartInput(
        video=Artifact(uri="s3://bucket/missing.mp4", content_type="video/mp4", sha256="0" * 64),
        title="P2",
    )
    archive = BilibiliArchiveSnapshot(
        aid=9,
        bvid="BVOLD",
        title="archive",
        parts=(BilibiliArchivePart(index=1, title="P1", remote_filename="old"),),
        archive={"aid": 9, "bvid": "BVOLD", "title": "archive"},
        videos=({"filename": "old", "title": "P1", "desc": ""},),
    )
    adapter = _adapter()
    with pytest.raises(BilibiliInputError, match="bvid does not match"):
        adapter.append(archive, BilibiliAppendRequest(bvid="BVOTHER", parts=(part,)), [missing])
    with pytest.raises(BilibiliInputError, match="part count changed"):
        adapter.append(
            archive,
            BilibiliAppendRequest(aid=9, expected_part_count=2, parts=(part,)),
            [missing],
        )
    with pytest.raises(BilibiliInputError, match="does not exist"):
        adapter.append(archive, BilibiliAppendRequest(aid=9, expected_part_count=1, parts=(part,)), [missing])
