"""Publication registry boundaries and a small Airflow metastore implementation."""

from __future__ import annotations

import hashlib
import json
from typing import Protocol

from homelab_video_contracts import BilibiliPublicationRecord


class BilibiliPublicationRegistry(Protocol):
    """Persistence boundary implemented by the workflow's database layer."""

    def get(
        self,
        *,
        source_video_id: str,
        account_id: str,
        request_sha256: str,
    ) -> BilibiliPublicationRecord | None: ...

    def upsert(self, record: BilibiliPublicationRecord) -> BilibiliPublicationRecord: ...


def publication_key(record: BilibiliPublicationRecord) -> tuple[str, str, str]:
    """Return the unique idempotency key for a publication record."""
    return record.source_video_id, record.account_id, record.request_sha256


def publication_storage_key(
    *,
    source_video_id: str,
    account_id: str,
    request_sha256: str,
) -> str:
    """Return a bounded Airflow Variable key without embedding user input."""
    canonical = json.dumps(
        [source_video_id, account_id, request_sha256],
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    return f"bilibili_publication_{digest}"


class AirflowVariablePublicationRegistry:
    """Persist records in Airflow Variables for low-concurrency workflows.

    Production deployments with concurrent writers should implement the same
    protocol with a transactional database table and a unique key constraint.
    """

    def __init__(self, *, key_prefix: str = "bilibili_publication_") -> None:
        if not key_prefix or any(character.isspace() for character in key_prefix):
            raise ValueError("key_prefix must be non-empty and contain no whitespace")
        self.key_prefix = key_prefix

    def _key(self, *, source_video_id: str, account_id: str, request_sha256: str) -> str:
        return publication_storage_key(
            source_video_id=source_video_id,
            account_id=account_id,
            request_sha256=request_sha256,
        ).replace("bilibili_publication_", self.key_prefix, 1)

    def get(
        self,
        *,
        source_video_id: str,
        account_id: str,
        request_sha256: str,
    ) -> BilibiliPublicationRecord | None:
        from airflow.models import Variable

        raw = Variable.get(
            self._key(
                source_video_id=source_video_id,
                account_id=account_id,
                request_sha256=request_sha256,
            ),
            default_var=None,
        )
        if raw is None:
            return None
        return BilibiliPublicationRecord.model_validate_json(raw)

    def upsert(self, record: BilibiliPublicationRecord) -> BilibiliPublicationRecord:
        from airflow.models import Variable

        Variable.set(
            self._key(
                source_video_id=record.source_video_id,
                account_id=record.account_id,
                request_sha256=record.request_sha256,
            ),
            record.model_dump_json(exclude_none=True),
        )
        return record
