"""biliup Python SDK adapter and provider-level publication types."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
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
        request: BilibiliUploadRequest,
        local_parts: Sequence[Path],
    ) -> BilibiliSubmissionReceipt: ...


def request_digest(request: BilibiliUploadRequest) -> str:
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
        self.cookie_path = cookie_path
        self.proxy = proxy
        self.submit_api = submit_api

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
            self._login(bili)
            payload = bili.myinfo()
            data = payload.get("data") if isinstance(payload, dict) else None
            account_id = str(data.get("mid")) if isinstance(data, dict) and data.get("mid") else None
            return BilibiliLoginStatus(ok=True, account_id=account_id, message="Bilibili login is valid")
        except BilibiliClientError as error:
            return BilibiliLoginStatus(ok=False, message=str(error))
        except Exception:
            return BilibiliLoginStatus(ok=False, message="Bilibili login check failed")

    def _new_video(self, request: BilibiliUploadRequest, bili_webup: Any) -> Any:
        video = bili_webup.Data()
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
        video.extra_fields = json.dumps(settings.extra_fields, ensure_ascii=False) if settings.extra_fields else ""
        return video

    @staticmethod
    def _require_sha256(value: str | None) -> str:
        if not value:
            raise BilibiliInputError("Bilibili artifacts must include sha256")
        return value

    @staticmethod
    def _receipt(
        response: dict[str, Any], title: str, parts: Sequence[BilibiliPartResult]
    ) -> BilibiliSubmissionReceipt:
        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict) or not data.get("aid"):
            raise BilibiliPolicyError("Bilibili returned a submission response without aid")
        aid = int(data["aid"])
        bvid = str(data.get("bvid") or data.get("bvid_str") or "")
        if not bvid:
            bvid = f"av{aid}"
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
        if aid <= 0:
            raise BilibiliInputError("archive aid must be positive")
        bili_webup, _ = self._modules()
        try:
            bili = bili_webup.BiliBili(bili_webup.Data())
            self._login(bili)
            data = bili.get_video_info(aid)
            pages = data.get("pages") or []
            parts = tuple(
                BilibiliArchivePart(
                    index=i,
                    title=str(page.get("part") or page.get("title") or f"P{i}"),
                    remote_filename=str(page.get("filename") or page.get("cid") or f"part-{i}"),
                    cid=int(page["cid"]) if page.get("cid") else None,
                )
                for i, page in enumerate(pages, start=1)
            )
            return BilibiliArchiveSnapshot(
                aid=int(data.get("aid", aid)),
                bvid=str(data.get("bvid") or ""),
                title=str(data.get("title") or ""),
                description=str(data.get("desc") or ""),
                tid=int(data["tid"]) if data.get("tid") else None,
                tags=tuple(
                    str(tag)
                    for tag in (
                        data.get("tags") or []
                        if isinstance(data.get("tags"), list)
                        else str(data.get("tag") or "").split(",")
                        if data.get("tag")
                        else []
                    )
                ),
                cover=data.get("pic"),
                copyright=int(data.get("copyright", 1)),
                source_url=data.get("source"),
                dynamic=str(data.get("dynamic") or ""),
                status=self._status(data.get("state")),
                parts=parts,
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
        if len(local_parts) != len(request.parts):
            raise BilibiliInputError("local_parts must have the same length as request.parts")
        bili_webup, _ = self._modules()
        try:
            video = self._new_video(request, bili_webup)
            bili = bili_webup.BiliBili(video)
            self._login(bili)
            for part, path in zip(request.parts, local_parts, strict=True):
                if not path.is_file():
                    raise BilibiliInputError(f"video part does not exist: {path}")
                uploaded = bili.upload_file(str(path))
                uploaded["title"] = part.title
                uploaded["desc"] = part.description
                video.append(uploaded)
            if cover_path is not None:
                video.cover = bili.cover_up(str(cover_path)).replace("http:", "")
            response = bili.submit(self.submit_api)
            results = tuple(
                BilibiliPartResult(
                    index=index,
                    title=part.title,
                    source_sha256=self._require_sha256(part.video.sha256),
                    remote_filename=str(uploaded.get("filename", uploaded.get("title", index))),
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
        """Append by submitting the complete archive, preserving old parts."""
        if archive.aid <= 0:
            raise BilibiliInputError("archive aid must be positive")
        if len(local_parts) != len(request.parts):
            raise BilibiliInputError("local_parts must have the same length as request.parts")
        bili_webup, bili_webup_sync = self._modules()
        try:
            video = bili_webup_sync.Data()
            video.aid = archive.aid
            video.title = archive.title
            video.desc = archive.description
            video.tid = archive.tid or request.tid
            video.tag = ",".join(archive.tags or request.tags)
            video.copyright = archive.copyright
            video.source = archive.source_url or ""
            video.dynamic = archive.dynamic
            video.cover = archive.cover or ""
            settings = archive.settings
            video.dolby = int(settings.dolby)
            video.hires = int(settings.lossless_music)
            video.no_reprint = int(settings.no_reprint)
            video.charging_pay = int(settings.charging_pay)
            video.extra_fields = json.dumps(settings.extra_fields, ensure_ascii=False) if settings.extra_fields else ""
            video.videos = [
                {"filename": part.remote_filename, "title": part.title, "desc": ""} for part in archive.parts
            ]
            uploader = bili_webup.BiliBili(bili_webup.Data())
            self._login(uploader)
            for part, path in zip(request.parts, local_parts, strict=True):
                uploaded = uploader.upload_file(str(path))
                video.videos.append({"filename": uploaded["filename"], "title": part.title, "desc": part.description})
            sync_uploader = bili_webup_sync.BiliBili(video)
            self._login(sync_uploader)
            response = sync_uploader.submit(self.submit_api, edit=True, videos=video)
            parts = archive.parts + tuple(
                BilibiliPartResult(
                    index=len(archive.parts) + index,
                    title=part.title,
                    source_sha256=self._require_sha256(part.video.sha256),
                    remote_filename=str(video.videos[-len(request.parts) + index - 1]["filename"]),
                )
                for index, part in enumerate(request.parts, start=1)
            )
            return self._receipt(response, archive.title, parts)
        except BilibiliClientError:
            raise
        except Exception as error:
            raise BilibiliPolicyError("Bilibili archive edit was rejected") from error
