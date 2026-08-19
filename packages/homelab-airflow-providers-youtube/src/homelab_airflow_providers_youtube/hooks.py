"""Read-only hook for the YouTube Data API v3."""

from __future__ import annotations

import re
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC
from datetime import datetime
from typing import Any

import requests
from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook
from homelab_video_contracts import YouTubeChannel
from homelab_video_contracts import YouTubeVideo


_DURATION_PATTERN = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+(?:\.\d+)?)S)?)?$"
)


@dataclass(frozen=True, slots=True)
class YouTubeConnectionConfig:
    """Resolved Data API settings."""

    api_key: str
    api_base_url: str
    timeout: float
    proxies: dict[str, str] | None
    max_retries: int
    retry_delay: float


class YouTubeHook(BaseHook):
    """Discover public YouTube channels and videos with an API key."""

    conn_name_attr = "youtube_conn_id"
    default_conn_name = "youtube_default"
    conn_type = "youtube"
    hook_name = "YouTube"

    def __init__(self, youtube_conn_id: str = default_conn_name) -> None:
        """Initialize the hook with an Airflow Connection ID."""
        super().__init__()
        self.youtube_conn_id = youtube_conn_id
        self._config: YouTubeConnectionConfig | None = None
        self._session: requests.Session | None = None

    @classmethod
    def get_ui_field_behaviour(cls) -> dict[str, Any]:
        """Describe the Airflow connection form."""
        return {
            "hidden_fields": ["host", "schema", "login", "port"],
            "relabeling": {"password": "YouTube Data API key"},
            "placeholders": {
                "password": "API key",
                "extra": "JSON with api_base_url, timeout, proxy, max_retries, and retry_delay",
            },
        }

    def get_connection_config(self) -> YouTubeConnectionConfig:
        """Resolve and validate connection settings without exposing the API key."""
        if self._config is not None:
            return self._config

        connection = self.get_connection(self.youtube_conn_id)
        if not connection.password:
            raise AirflowException(f"Connection {self.youtube_conn_id!r} must define the API key in Password")

        extra = connection.extra_dejson
        timeout = float(extra.get("timeout", 30))
        max_retries = int(extra.get("max_retries", 2))
        retry_delay = float(extra.get("retry_delay", 1))
        if timeout <= 0:
            raise AirflowException("YouTube connection timeout must be greater than zero")
        if not 0 <= max_retries <= 5:
            raise AirflowException("YouTube connection max_retries must be between 0 and 5")
        if retry_delay < 0:
            raise AirflowException("YouTube connection retry_delay must not be negative")

        proxy = extra.get("proxy")
        if proxy is not None and (not isinstance(proxy, str) or not proxy.strip()):
            raise AirflowException("YouTube connection proxy must be a non-empty URL string")
        proxies = {"http": proxy, "https": proxy} if proxy else None

        api_base_url = str(extra.get("api_base_url", "https://www.googleapis.com/youtube/v3")).rstrip("/")
        if not api_base_url.startswith(("http://", "https://")):
            raise AirflowException("YouTube connection api_base_url must be an HTTP(S) URL")

        self._config = YouTubeConnectionConfig(
            api_key=connection.password,
            api_base_url=api_base_url,
            timeout=timeout,
            proxies=proxies,
            max_retries=max_retries,
            retry_delay=retry_delay,
        )
        return self._config

    def get_conn(self) -> requests.Session:
        """Return a reusable HTTP session."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({"Accept": "application/json"})
        return self._session

    def test_connection(self) -> tuple[bool, str]:
        """Verify the API key with a minimal read-only request."""
        try:
            self._request("videos", {"part": "id", "id": "dQw4w9WgXcQ"})
        except AirflowException as error:
            return False, str(error)
        return True, "YouTube Data API is reachable"

    def _request(self, resource: str, params: dict[str, Any]) -> dict[str, Any]:
        config = self.get_connection_config()
        request_params = {**params, "key": config.api_key}
        url = f"{config.api_base_url}/{resource}"

        for attempt in range(config.max_retries + 1):
            try:
                response = self.get_conn().get(
                    url,
                    params=request_params,
                    timeout=config.timeout,
                    proxies=config.proxies,
                )
            except (requests.ConnectionError, requests.Timeout) as error:
                if attempt >= config.max_retries:
                    raise AirflowException(f"YouTube Data API request failed: {error.__class__.__name__}") from error
                self._sleep_before_retry(config, attempt)
                continue
            except requests.RequestException as error:
                raise AirflowException(f"YouTube Data API request failed: {error.__class__.__name__}") from error

            if (response.status_code == 429 or response.status_code >= 500) and attempt < config.max_retries:
                response.close()
                self._sleep_before_retry(config, attempt)
                continue
            if response.status_code >= 400:
                raise AirflowException(f"YouTube Data API request failed: {self._error_detail(response)}")
            try:
                payload = response.json()
            except ValueError as error:
                raise AirflowException("YouTube Data API returned invalid JSON") from error
            if not isinstance(payload, dict):
                raise AirflowException("YouTube Data API returned a non-object JSON response")
            return payload

        raise AssertionError("YouTube request retry loop exited unexpectedly")

    @staticmethod
    def _sleep_before_retry(config: YouTubeConnectionConfig, attempt: int) -> None:
        time.sleep(config.retry_delay * (2**attempt))

    @staticmethod
    def _error_detail(response: requests.Response) -> str:
        reason: str | None = None
        message: str | None = None
        try:
            error = response.json().get("error", {})
            message = error.get("message")
            errors = error.get("errors") or []
            if errors:
                reason = errors[0].get("reason")
        except (AttributeError, IndexError, TypeError, ValueError):
            pass
        suffix = ": ".join(part for part in (reason, message) if part)
        return f"HTTP {response.status_code}" + (f" ({suffix[:300]})" if suffix else "")

    def get_channel(self, channel_id: str) -> YouTubeChannel:
        """Return one channel and its uploads playlist identity."""
        normalized_id = _required_id(channel_id, "channel_id")
        return self._get_channel({"id": normalized_id}, f"YouTube channel {normalized_id!r}")

    def get_channel_by_handle(self, handle: str) -> YouTubeChannel:
        """Resolve a human-readable handle and return its channel metadata."""
        normalized_handle = _required_handle(handle)
        return self._get_channel(
            {"forHandle": normalized_handle},
            f"YouTube handle {'@' + normalized_handle!r}",
        )

    def _get_channel(self, filter_params: dict[str, str], not_found_label: str) -> YouTubeChannel:
        """Return one channel selected by an API-supported filter."""
        payload = self._request(
            "channels",
            {"part": "snippet,contentDetails", **filter_params, "maxResults": 1},
        )
        items = payload.get("items") or []
        if not items:
            raise AirflowException(f"{not_found_label} was not found")

        item = items[0]
        snippet = item.get("snippet") or {}
        uploads = ((item.get("contentDetails") or {}).get("relatedPlaylists") or {}).get("uploads")
        title = snippet.get("title")
        if not uploads or not title:
            raise AirflowException(f"{not_found_label} returned incomplete metadata")
        published_at = snippet.get("publishedAt")
        channel_id = _required_id(item.get("id"), "channel_id")
        return YouTubeChannel(
            channel_id=channel_id,
            title=title,
            description=snippet.get("description") or None,
            published_at=_parse_datetime(published_at) if published_at else None,
            uploads_playlist_id=uploads,
        )

    def get_uploads_playlist_id(self, channel_id: str) -> str:
        """Return the channel uploads playlist ID."""
        return self.get_channel(channel_id).uploads_playlist_id

    def get_videos(self, video_ids: Sequence[str]) -> list[YouTubeVideo]:
        """Return normalized metadata for up to 200 video IDs."""
        normalized_ids = list(dict.fromkeys(_required_id(value, "video_id") for value in video_ids))
        if len(normalized_ids) > 200:
            raise ValueError("video_ids must contain at most 200 unique IDs")

        videos: dict[str, YouTubeVideo] = {}
        for offset in range(0, len(normalized_ids), 50):
            batch = normalized_ids[offset : offset + 50]
            payload = self._request(
                "videos",
                {"part": "snippet,contentDetails", "id": ",".join(batch), "maxResults": len(batch)},
            )
            for item in payload.get("items") or []:
                video = _parse_video(item)
                videos[video.video_id] = video
        return [videos[video_id] for video_id in normalized_ids if video_id in videos]

    def list_playlist_videos(
        self,
        playlist_id: str,
        *,
        published_after: datetime | str | None = None,
        published_before: datetime | str | None = None,
        max_results: int = 50,
    ) -> list[YouTubeVideo]:
        """List videos in playlist order and filter by a half-open publication window."""
        normalized_playlist_id = _required_id(playlist_id, "playlist_id")
        after = coerce_datetime(published_after, "published_after")
        before = coerce_datetime(published_before, "published_before")
        if after and before and after >= before:
            raise ValueError("published_after must be earlier than published_before")
        if not 1 <= max_results <= 200:
            raise ValueError("max_results must be between 1 and 200")

        matches: list[YouTubeVideo] = []
        seen_video_ids: set[str] = set()
        page_token: str | None = None
        seen_page_tokens: set[str] = set()
        while len(matches) < max_results:
            params: dict[str, Any] = {
                "part": "contentDetails",
                "playlistId": normalized_playlist_id,
                "maxResults": 50,
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._request("playlistItems", params)
            candidate_ids = [item.get("contentDetails", {}).get("videoId") for item in payload.get("items") or []]
            candidate_ids = [video_id for video_id in candidate_ids if video_id and video_id not in seen_video_ids]
            seen_video_ids.update(candidate_ids)

            reached_before_window = False
            for video in self.get_videos(candidate_ids):
                if after and video.published_at < after:
                    reached_before_window = True
                    continue
                if before and video.published_at >= before:
                    continue
                matches.append(video)
                if len(matches) >= max_results:
                    break

            # A channel's uploads playlist is ordered newest first. Once a page
            # reaches videos older than the lower bound, later pages cannot match.
            if reached_before_window:
                break

            next_page_token = payload.get("nextPageToken")
            if not next_page_token or next_page_token in seen_page_tokens:
                break
            seen_page_tokens.add(next_page_token)
            page_token = next_page_token
        return matches

    def list_channel_videos(
        self,
        channel_id: str,
        *,
        published_after: datetime | str | None = None,
        published_before: datetime | str | None = None,
        max_results: int = 50,
    ) -> list[YouTubeVideo]:
        """List normalized uploads for one channel."""
        playlist_id = self.get_uploads_playlist_id(channel_id)
        return self.list_playlist_videos(
            playlist_id,
            published_after=published_after,
            published_before=published_before,
            max_results=max_results,
        )


def _parse_video(item: dict[str, Any]) -> YouTubeVideo:
    video_id = _required_id(item.get("id"), "video_id")
    snippet = item.get("snippet") or {}
    channel_id = _required_id(snippet.get("channelId"), "channel_id")
    title = snippet.get("title")
    published_at = snippet.get("publishedAt")
    if not title or not published_at:
        raise AirflowException(f"YouTube video {video_id!r} returned incomplete metadata")
    return YouTubeVideo(
        video_id=video_id,
        channel_id=channel_id,
        channel_title=snippet.get("channelTitle") or None,
        title=title,
        description=snippet.get("description") or None,
        published_at=_parse_datetime(published_at),
        source_url=f"https://www.youtube.com/watch?v={video_id}",
        thumbnail_url=_thumbnail_url(snippet.get("thumbnails") or {}),
        duration_ms=_parse_duration_ms((item.get("contentDetails") or {}).get("duration")),
        default_language=snippet.get("defaultLanguage") or snippet.get("defaultAudioLanguage"),
    )


def _thumbnail_url(thumbnails: dict[str, Any]) -> str | None:
    for name in ("maxres", "standard", "high", "medium", "default"):
        url = (thumbnails.get(name) or {}).get("url")
        if url:
            return url
    return None


def _parse_duration_ms(value: str | None) -> int | None:
    if value is None:
        return None
    match = _DURATION_PATTERN.fullmatch(value)
    if match is None:
        raise AirflowException(f"YouTube returned an unsupported duration {value!r}")
    parts = {name: float(number or 0) for name, number in match.groupdict().items()}
    seconds = parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]
    return round(seconds * 1000)


def coerce_datetime(value: datetime | str | None, label: str) -> datetime | None:
    """Normalize an optional ISO timestamp to an aware UTC datetime."""
    if value is None:
        return None
    parsed = _parse_datetime(value) if isinstance(value, str) else value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AirflowException(f"YouTube returned an invalid timestamp {value!r}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AirflowException(f"YouTube returned a timestamp without timezone: {value!r}")
    return parsed.astimezone(UTC)


def _required_id(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    normalized = value.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", normalized):
        raise ValueError(f"{label} contains unsupported characters")
    return normalized


def _required_handle(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("handle must be a non-empty string")
    normalized = value.strip()
    if normalized.startswith("@"):
        normalized = normalized[1:]
    if not normalized:
        raise ValueError("handle must contain characters after '@'")
    if normalized.startswith("@") or "/" in normalized or any(character.isspace() for character in normalized):
        raise ValueError("handle must be a handle name, not a URL")
    return normalized
