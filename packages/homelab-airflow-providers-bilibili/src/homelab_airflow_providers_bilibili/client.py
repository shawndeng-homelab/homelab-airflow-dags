"""biliup Python SDK adapter and provider-level publication types."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import fields
from pathlib import Path
from typing import Any
from typing import Protocol

from homelab_video_contracts import BilibiliAppendRequest
from homelab_video_contracts import BilibiliArchivePart
from homelab_video_contracts import BilibiliArchiveSnapshot
from homelab_video_contracts import BilibiliPartResult
from homelab_video_contracts import BilibiliPublicationStatus
from homelab_video_contracts import BilibiliPublishSettings
from homelab_video_contracts import BilibiliUploadRequest


class BilibiliClientError(Exception):
    """Base error raised by the SDK adapter."""


class BilibiliAuthenticationError(BilibiliClientError):
    """The mounted credentials cannot authenticate the account."""


class BilibiliInputError(BilibiliClientError):
    """The request or local media cannot be accepted by Bilibili."""


class BilibiliPolicyError(BilibiliClientError):
    """Bilibili rejected the request for policy or account reasons."""


class BilibiliTransientError(BilibiliClientError):
    """A network or rate-limit failure that may be retried safely."""


@dataclass(frozen=True, slots=True)
class BilibiliLoginStatus:
    """Small, log-safe account status returned by a login check."""

    ok: bool
    account_id: str | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class BilibiliSubmissionReceipt:
    """Normalized response from a new or edited submission."""

    aid: int
    bvid: str
    title: str
    status: BilibiliPublicationStatus
    parts: tuple[BilibiliPartResult | BilibiliArchivePart, ...]
    raw_response: dict[str, Any]


class BilibiliClient(Protocol):
    """Minimal SDK-independent interface consumed by the Airflow Hook."""

    def check_login(self) -> BilibiliLoginStatus: ...

    def get_archive(self, aid: int) -> BilibiliArchiveSnapshot: ...

    def publish(
        self,
        request: BilibiliUploadRequest,
        local_parts: Sequence[Path],
        cover_path: Path | None = None,
    ) -> BilibiliSubmissionReceipt: ...

    def append(
        self,
        archive: BilibiliArchiveSnapshot,
        request: BilibiliAppendRequest,
        local_parts: Sequence[Path],
    ) -> BilibiliSubmissionReceipt: ...


def request_digest(request: BilibiliUploadRequest | BilibiliAppendRequest) -> str:
    """Return a stable idempotency digest without serializing SDK objects."""
    payload = request.model_dump(mode="json", exclude_none=True)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


class BiliupSdkAdapter:
    """Adapt biliup's Python uploader modules to the stable client protocol.

    Imports are deliberately lazy because Airflow provider discovery must not
    import Pillow, rsa, or the biliup native extension.
    """

    def __init__(self, cookie_path: Path, *, proxy: str | None = None, submit_api: str = "web") -> None:
        if submit_api not in {"web", "client"}:
            raise BilibiliInputError("submit_api must be web or client")
        self.cookie_path = cookie_path
        self.proxy = proxy
        self.submit_api = submit_api

    def _configure_proxy(self, bili: Any) -> None:
        if not self.proxy:
            return
        session = getattr(bili, "_BiliBili__session", None)
        if session is None or not hasattr(session, "proxies"):
            raise BilibiliClientError("biliup 1.2.2 uploader does not expose a proxy-capable session")
        session.proxies.update({"http": self.proxy, "https": self.proxy})

    def _modules(self) -> tuple[Any, Any]:
        try:
            from biliup.plugins import bili_webup
            from biliup.plugins import bili_webup_sync
        except ImportError as error:
            raise BilibiliClientError("biliup Python SDK is not installed") from error
        return bili_webup, bili_webup_sync

    def _login(self, bili: Any) -> None:
        if not self.cookie_path.is_file():
            raise BilibiliAuthenticationError(f"biliup credential file is missing: {self.cookie_path}")
        bili.persistence_path = str(self.cookie_path)
        try:
            bili.load()
            if not bili.cookies:
                raise BilibiliAuthenticationError("biliup credential file contains no cookies")
            bili.login_by_cookies(bili.cookies)
        except BilibiliAuthenticationError:
            raise
        except Exception as error:
            raise BilibiliAuthenticationError("biliup credentials were rejected") from error

    def check_login(self) -> BilibiliLoginStatus:
        bili_webup, _ = self._modules()
        try:
            bili = bili_webup.BiliBili(bili_webup.Data())
            self._configure_proxy(bili)
            self._login(bili)
            payload = bili.myinfo()
            data = payload.get("data") if isinstance(payload, dict) else None
            account_id = str(data.get("mid")) if isinstance(data, dict) and data.get("mid") else None
            return BilibiliLoginStatus(ok=True, account_id=account_id, message="Bilibili login is valid")
        except BilibiliClientError as error:
            return BilibiliLoginStatus(ok=False, message=str(error))
        except Exception:
            return BilibiliLoginStatus(ok=False, message="Bilibili login check failed")

    def _settings_extra_fields(self, settings: BilibiliPublishSettings) -> dict[str, object]:
        reserved = {
            "aid",
            "copyright",
            "source",
            "tid",
            "cover",
            "title",
            "desc_format_id",
            "desc",
            "desc_v2",
            "dynamic",
            "subtitle",
            "tag",
            "videos",
            "dtime",
            "dolby",
            "hires",
            "no_reprint",
            "is_only_self",
            "charging_pay",
            "up_close_reply",
            "up_selection_reply",
            "up_close_danmu",
        }
        conflicts = reserved.intersection(settings.extra_fields)
        if conflicts:
            raise BilibiliInputError(f"settings.extra_fields cannot override SDK fields: {sorted(conflicts)}")
        if self.submit_api == "web" and (settings.close_reply or settings.selection_reply or settings.close_danmu):
            raise BilibiliInputError("reply and danmu moderation settings require submit_api=client")
        extra_fields = dict(settings.extra_fields)
        if settings.close_reply:
            extra_fields["up_close_reply"] = True
        if settings.selection_reply:
            extra_fields["up_selection_reply"] = True
        if settings.close_danmu:
            extra_fields["up_close_danmu"] = True
        return extra_fields

    def _new_video(self, request: BilibiliUploadRequest, bili_webup_sync: Any) -> Any:
        video = bili_webup_sync.Data()
        video.title = request.title
        video.desc = request.description
        video.tid = request.tid
        video.tag = ",".join(request.tags)
        video.copyright = request.copyright
        video.source = request.source_url or ""
        video.dynamic = request.dynamic
        if request.scheduled_at is not None:
            video.dtime = int(request.scheduled_at.timestamp())
        settings: BilibiliPublishSettings = request.settings
        video.dolby = int(settings.dolby)
        video.hires = int(settings.lossless_music)
        video.no_reprint = int(settings.no_reprint)
        video.charging_pay = int(settings.charging_pay)
        extra_fields = self._settings_extra_fields(settings)
        video.extra_fields = json.dumps(extra_fields, ensure_ascii=False) if extra_fields else ""
        return video

    def _new_uploader(self, module: Any, video: Any) -> Any:
        uploader = module.BiliBili(video)
        self._configure_proxy(uploader)
        self._login(uploader)
        return uploader

    @classmethod
    def _validate_local_parts(cls, request_parts: Sequence[Any], local_parts: Sequence[Path]) -> None:
        if len(local_parts) != len(request_parts):
            raise BilibiliInputError("local_parts must have the same length as request.parts")
        for part, path in zip(request_parts, local_parts, strict=True):
            if not path.is_file():
                raise BilibiliInputError(f"video part does not exist: {path}")
            expected_sha256 = cls._require_sha256(part.video.sha256)
            if part.video.size is not None and path.stat().st_size != part.video.size:
                raise BilibiliInputError(f"video part size does not match artifact: {path}")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            if digest.hexdigest() != expected_sha256:
                raise BilibiliInputError(f"video part sha256 does not match artifact: {path}")

    @staticmethod
    def _creative_archive_data(bili: Any, aid: int) -> dict[str, Any]:
        session = getattr(bili, "_BiliBili__session", None)
        if session is None:
            raise BilibiliClientError("biliup 1.2.2 session is unavailable for archive lookup")
        response = session.get(
            "https://member.bilibili.com/x/web/archive/view",
            params={"aid": aid},
            timeout=10,
        ).json()
        if not isinstance(response, dict) or response.get("code") != 0 or not isinstance(response.get("data"), dict):
            raise BilibiliPolicyError("Bilibili creative-center archive lookup was rejected")
        return response["data"]

    @staticmethod
    def _require_sha256(value: str | None) -> str:
        if not value:
            raise BilibiliInputError("Bilibili artifacts must include sha256")
        return value

    @staticmethod
    def _receipt(
        response: dict[str, Any],
        title: str,
        parts: Sequence[BilibiliPartResult | BilibiliArchivePart],
        *,
        fallback_bvid: str = "",
    ) -> BilibiliSubmissionReceipt:
        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict) or not data.get("aid"):
            raise BilibiliPolicyError("Bilibili returned a submission response without aid")
        aid = int(data["aid"])
        bvid = str(data.get("bvid") or data.get("bvid_str") or fallback_bvid)
        if not bvid:
            raise BilibiliPolicyError("Bilibili returned a submission response without bvid")
        return BilibiliSubmissionReceipt(
            aid=aid,
            bvid=bvid,
            title=title,
            status=BilibiliPublicationStatus.SUBMITTED,
            parts=tuple(parts),
            raw_response=response,
        )

    @staticmethod
    def _status(state: object) -> BilibiliPublicationStatus:
        if state == 0:
            return BilibiliPublicationStatus.PUBLISHED
        if state in {-1, -2, -3}:
            return BilibiliPublicationStatus.REJECTED
        if isinstance(state, int):
            return BilibiliPublicationStatus.REVIEWING
        return BilibiliPublicationStatus.UNKNOWN

    def get_archive(self, aid: int) -> BilibiliArchiveSnapshot:
        """Fetch owner-only edit data from the creative center."""
        if aid <= 0:
            raise BilibiliInputError("archive aid must be positive")
        _, bili_webup_sync = self._modules()
        try:
            bili = self._new_uploader(bili_webup_sync, bili_webup_sync.Data())
            data = self._creative_archive_data(bili, aid)
            archive = data.get("archive")
            videos = data.get("videos")
            if not isinstance(archive, dict) or not isinstance(videos, list) or not videos:
                raise BilibiliPolicyError("creative-center response omitted archive or videos")
            archive_aid = int(archive.get("aid") or aid)
            if archive_aid != aid:
                raise BilibiliPolicyError("creative-center response returned a different aid")
            bvid = str(archive.get("bvid") or "")
            title = str(archive.get("title") or "")
            if not bvid or not title:
                raise BilibiliPolicyError("creative-center response omitted bvid or title")
            parts: list[BilibiliArchivePart] = []
            preserved_videos: list[dict[str, object]] = []
            for index, item in enumerate(videos, start=1):
                if not isinstance(item, dict) or not item.get("filename"):
                    raise BilibiliPolicyError("creative-center response omitted a part filename")
                preserved = dict(item)
                preserved_videos.append(preserved)
                parts.append(
                    BilibiliArchivePart(
                        index=index,
                        title=str(item.get("title") or f"P{index}"),
                        description=str(item.get("desc") or ""),
                        remote_filename=str(item["filename"]),
                        cid=int(item["cid"]) if item.get("cid") else None,
                    )
                )
            tag_value = archive.get("tag") or archive.get("tags") or ""
            tags = (
                tuple(str(tag) for tag in tag_value)
                if isinstance(tag_value, list)
                else tuple(tag for tag in str(tag_value).split(",") if tag)
            )
            settings = BilibiliPublishSettings(
                dolby=bool(archive.get("dolby", 0)),
                lossless_music=bool(archive.get("hires", 0)),
                no_reprint=bool(archive.get("no_reprint", 0)),
                charging_pay=bool(archive.get("charging_pay", 0)),
                close_reply=bool(archive.get("up_close_reply", 0)),
                selection_reply=bool(archive.get("up_selection_reply", 0)),
                close_danmu=bool(archive.get("up_close_danmu", 0)),
            )
            return BilibiliArchiveSnapshot(
                aid=archive_aid,
                bvid=bvid,
                title=title,
                description=str(archive.get("desc") or ""),
                tid=int(archive["tid"]) if archive.get("tid") else None,
                tags=tags,
                cover=str(archive.get("cover") or "") or None,
                copyright=int(archive.get("copyright", 1)),
                source_url=str(archive.get("source") or "") or None,
                dynamic=str(archive.get("dynamic") or ""),
                settings=settings,
                status=self._status(archive.get("state")),
                parts=tuple(parts),
                archive=dict(archive),
                videos=tuple(preserved_videos),
            )
        except BilibiliClientError:
            raise
        except (TimeoutError, ConnectionError) as error:
            raise BilibiliTransientError("Bilibili archive query failed") from error
        except Exception as error:
            raise BilibiliPolicyError("Bilibili archive query was rejected") from error

    def publish(
        self, request: BilibiliUploadRequest, local_parts: Sequence[Path], cover_path: Path | None = None
    ) -> BilibiliSubmissionReceipt:
        self._validate_local_parts(request.parts, local_parts)
        if cover_path is not None and not cover_path.is_file():
            raise BilibiliInputError(f"cover does not exist: {cover_path}")
        bili_webup, bili_webup_sync = self._modules()
        try:
            video = self._new_video(request, bili_webup_sync)
            uploader = self._new_uploader(bili_webup, bili_webup.Data())
            for part, path in zip(request.parts, local_parts, strict=True):
                uploaded = uploader.upload_file(str(path))
                uploaded["title"] = part.title
                uploaded["desc"] = part.description
                video.append(uploaded)
            if cover_path is not None:
                video.cover = uploader.cover_up(str(cover_path)).replace("http:", "")
            submitter = self._new_uploader(bili_webup_sync, video)
            response = submitter.submit(self.submit_api, videos=video)
            results = tuple(
                BilibiliPartResult(
                    index=index,
                    title=part.title,
                    source_sha256=self._require_sha256(part.video.sha256),
                    remote_filename=str(uploaded["filename"]),
                )
                for index, (part, uploaded) in enumerate(zip(request.parts, video.videos, strict=True), start=1)
            )
            return self._receipt(response, request.title, results)
        except BilibiliClientError:
            raise
        except (TimeoutError, ConnectionError) as error:
            raise BilibiliTransientError("Bilibili upload request failed") from error
        except Exception as error:
            raise BilibiliPolicyError("Bilibili rejected the submission") from error

    def append(
        self, archive: BilibiliArchiveSnapshot, request: BilibiliAppendRequest, local_parts: Sequence[Path]
    ) -> BilibiliSubmissionReceipt:
        """Append by editing the complete creative-center payload."""
        if request.aid is not None and request.aid != archive.aid:
            raise BilibiliInputError("append request aid does not match archive")
        if request.bvid is not None and request.bvid != archive.bvid:
            raise BilibiliInputError("append request bvid does not match archive")
        if request.expected_part_count is not None and request.expected_part_count != len(archive.videos):
            raise BilibiliInputError("Bilibili archive part count changed; refresh snapshot before appending")
        if not archive.archive or not archive.videos or len(archive.videos) != len(archive.parts):
            raise BilibiliInputError("append requires complete creative-center archive and videos data")
        self._validate_local_parts(request.parts, local_parts)
        if self.submit_api == "web" and (
            archive.settings.close_reply or archive.settings.selection_reply or archive.settings.close_danmu
        ):
            raise BilibiliInputError("archive uses moderation settings that require submit_api=client")
        bili_webup, bili_webup_sync = self._modules()
        try:
            payload = dict(archive.archive)
            payload["aid"] = archive.aid
            payload.pop("limited_free", None)
            data_fields = {item.name for item in fields(bili_webup_sync.Data) if item.init}
            constructor = {
                key: value
                for key, value in payload.items()
                if key in data_fields and key not in {"extra_fields", "videos", "subtitle"}
            }
            preserved_extra_fields = payload.get("extra_fields") or {}
            if isinstance(preserved_extra_fields, str):
                preserved_extra_fields = json.loads(preserved_extra_fields)
            if not isinstance(preserved_extra_fields, dict):
                raise BilibiliInputError("creative-center extra_fields must be a JSON object")
            extra_fields = {
                key: value
                for key, value in payload.items()
                if key not in data_fields and key not in {"videos", "limited_free", "subtitle"}
            }
            extra_fields = {**preserved_extra_fields, **extra_fields}
            constructor["extra_fields"] = json.dumps(extra_fields, ensure_ascii=False) if extra_fields else ""
            video = bili_webup_sync.Data(**constructor)
            if isinstance(payload.get("subtitle"), dict):
                video.subtitle = dict(payload["subtitle"])
            video.aid = archive.aid
            video.videos = [dict(item) for item in archive.videos]
            uploader = self._new_uploader(bili_webup, bili_webup.Data())
            uploaded_parts: list[dict[str, Any]] = []
            for part, path in zip(request.parts, local_parts, strict=True):
                uploaded = dict(uploader.upload_file(str(path)))
                uploaded["title"] = part.title
                uploaded["desc"] = part.description
                video.videos.append(uploaded)
                uploaded_parts.append(uploaded)
            submitter = self._new_uploader(bili_webup_sync, video)
            response = submitter.submit(self.submit_api, edit=True, videos=video)
            parts = archive.parts + tuple(
                BilibiliPartResult(
                    index=len(archive.parts) + index,
                    title=part.title,
                    source_sha256=self._require_sha256(part.video.sha256),
                    remote_filename=str(uploaded["filename"]),
                )
                for index, (part, uploaded) in enumerate(zip(request.parts, uploaded_parts, strict=True), start=1)
            )
            return self._receipt(response, archive.title, parts, fallback_bvid=archive.bvid)
        except BilibiliClientError:
            raise
        except (TimeoutError, ConnectionError) as error:
            raise BilibiliTransientError("Bilibili archive edit failed") from error
        except Exception as error:
            raise BilibiliPolicyError("Bilibili archive edit was rejected") from error
