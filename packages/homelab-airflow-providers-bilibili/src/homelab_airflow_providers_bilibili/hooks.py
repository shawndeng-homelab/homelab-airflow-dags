"""Airflow Hook for the biliup-backed Bilibili publisher."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook
from homelab_video_contracts import BilibiliAppendRequest
from homelab_video_contracts import BilibiliArchiveSnapshot
from homelab_video_contracts import BilibiliUploadRequest

from homelab_airflow_providers_bilibili.client import BilibiliClient
from homelab_airflow_providers_bilibili.client import BilibiliClientError
from homelab_airflow_providers_bilibili.client import BilibiliLoginStatus
from homelab_airflow_providers_bilibili.client import BilibiliSubmissionReceipt
from homelab_airflow_providers_bilibili.client import BiliupSdkAdapter


@dataclass(frozen=True, slots=True)
class BilibiliConnectionConfig:
    """Validated non-secret settings from an Airflow Connection."""

    credential_path: Path
    account_id: str
    proxy: str | None
    submit_api: str


class BilibiliHook(BaseHook):
    """Use biliup through a stable Airflow-facing interface."""

    conn_name_attr = "bilibili_conn_id"
    default_conn_name = "bilibili_default"
    conn_type = "bilibili"
    hook_name = "Bilibili"

    def __init__(self, bilibili_conn_id: str = default_conn_name, *, client: BilibiliClient | None = None) -> None:
        super().__init__()
        self.bilibili_conn_id = bilibili_conn_id
        self._client = client

    @classmethod
    def get_ui_field_behaviour(cls) -> dict[str, Any]:
        """Describe the connection form without exposing cookie contents."""
        return {
            "hidden_fields": ["host", "schema", "login", "port", "password"],
            "relabeling": {"extra": "JSON with credential_path, account_id, proxy, submit_api"},
            "placeholders": {"extra": '{"credential_path":"/var/run/secrets/bilibili/cookies.json"}'},
        }

    def get_connection_config(self) -> BilibiliConnectionConfig:
        """Resolve and validate the mounted credential path."""
        connection = self.get_connection(self.bilibili_conn_id)
        extra = connection.extra_dejson
        credential_path = extra.get("credential_path") or extra.get("credential_secret_path")
        if not isinstance(credential_path, str) or not credential_path.strip():
            raise AirflowException("Bilibili connection must define extra.credential_path")
        account_id = extra.get("account_id", "default")
        if not isinstance(account_id, str) or not account_id.strip():
            raise AirflowException("Bilibili connection account_id must be a non-empty string")
        proxy = extra.get("proxy")
        if proxy is not None and (not isinstance(proxy, str) or not proxy.strip()):
            raise AirflowException("Bilibili connection proxy must be a non-empty URL string")
        submit_api = extra.get("submit_api", "web")
        if submit_api not in {"web", "client"}:
            raise AirflowException("Bilibili connection submit_api must be web or client")
        return BilibiliConnectionConfig(Path(credential_path), account_id, proxy, submit_api)

    def get_conn(self) -> BilibiliClient:
        """Return the lazily-created SDK adapter."""
        if self._client is None:
            config = self.get_connection_config()
            self._client = BiliupSdkAdapter(config.credential_path, proxy=config.proxy, submit_api=config.submit_api)
        return self._client

    def get_archive(self, aid: int) -> BilibiliArchiveSnapshot:
        """Fetch and normalize a remote archive snapshot."""
        try:
            return self.get_conn().get_archive(aid)
        except BilibiliClientError as error:
            raise AirflowException(str(error)) from error

    def check_login(self) -> BilibiliLoginStatus:
        """Perform a read-only credential check."""
        return self.get_conn().check_login()

    def test_connection(self) -> tuple[bool, str]:
        """Return a log-safe Airflow connection test result."""
        try:
            status = self.check_login()
        except (AirflowException, BilibiliClientError) as error:
            return False, str(error)
        return status.ok, status.message

    def publish(
        self, request: BilibiliUploadRequest, local_parts: Sequence[Path], cover_path: Path | None = None
    ) -> BilibiliSubmissionReceipt:
        """Publish one complete稿件 and normalize SDK errors."""
        try:
            return self.get_conn().publish(request, local_parts, cover_path)
        except BilibiliClientError as error:
            raise AirflowException(str(error)) from error

    def append(
        self, archive: BilibiliArchiveSnapshot, request: BilibiliAppendRequest, local_parts: Sequence[Path]
    ) -> BilibiliSubmissionReceipt:
        """Append parts by editing the complete remote稿件."""
        try:
            return self.get_conn().append(archive, request, local_parts)
        except BilibiliClientError as error:
            raise AirflowException(str(error)) from error
