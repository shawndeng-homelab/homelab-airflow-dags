"""EODHD REST client independent from Airflow runtime state."""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from datetime import UTC
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urljoin

import requests

from homelab_airflow_providers_financial_data.models import EodhdConnectionConfig
from homelab_airflow_providers_financial_data.models import EodhdOptionEodRequest
from homelab_airflow_providers_financial_data.models import RawPage


class EodhdClient:
    """Fetch EODHD Marketplace option pages without exposing credentials."""

    def __init__(self, config: EodhdConnectionConfig, session: requests.Session | None = None) -> None:
        """Create a client with an owned or caller-provided HTTP session."""
        self.config = config
        self._session = session or self._new_session(config)
        self._owns_session = session is None

    @classmethod
    def from_environment(cls) -> EodhdClient:
        """Create a client from the documented EODHD environment variables."""
        try:
            config = EodhdConnectionConfig(
                api_token=os.environ.get("EODHD_API_TOKEN", ""),
                base_url=os.environ.get("EODHD_BASE_URL", "https://eodhd.com/api/"),
                timeout=float(os.environ.get("EODHD_TIMEOUT", "30")),
                max_retries=int(os.environ.get("EODHD_MAX_RETRIES", "4")),
                page_limit=int(os.environ.get("EODHD_PAGE_LIMIT", "1000")),
            )
        except (TypeError, ValueError):
            raise ValueError("Invalid EODHD environment configuration") from None
        return cls(config)

    def __enter__(self) -> EodhdClient:
        """Return the client for context-managed usage."""
        return self

    def __exit__(self, *args: object) -> None:
        """Close an owned session after use."""
        self.close()

    @staticmethod
    def _new_session(config: EodhdConnectionConfig) -> requests.Session:
        session = requests.Session()
        session.headers.update({"Accept": "application/json", "User-Agent": "homelab-airflow-financial-data/0.2"})
        if config.proxy:
            session.proxies.update({"http": str(config.proxy), "https": str(config.proxy)})
        session.verify = config.verify
        return session

    @property
    def session(self) -> requests.Session:
        """Return the configured requests session without adding credentials to headers."""
        return self._session

    def close(self) -> None:
        """Release an internally created HTTP session."""
        if self._owns_session:
            self._session.close()

    def test_connection(self) -> tuple[bool, str]:
        """Validate credentials with a read-only API endpoint."""
        try:
            self._request_json("user/")
        except RuntimeError as error:
            return False, str(error)
        return True, "EODHD credentials were accepted"

    def iter_option_eod_pages(self, request: EodhdOptionEodRequest) -> Iterator[RawPage]:
        """Yield JSON:API pages with checked offset pagination."""
        offset = 0
        page_number = 0
        while True:
            payload = self._request_json(
                "mp/unicornbay/options/eod",
                {
                    "filter[underlying_symbol]": request.underlying_symbol.upper(),
                    "filter[tradetime_from]": request.quote_date.isoformat(),
                    "filter[tradetime_to]": request.quote_date.isoformat(),
                    "page[offset]": str(offset),
                    "page[limit]": str(self.config.page_limit),
                    "sort": "exp_date",
                    "fmt": "json",
                },
            )
            records, next_offset = self._extract_page(payload, offset)
            page_number += 1
            yield RawPage(
                page_number=page_number,
                records=tuple(records),
                payload=payload,
                fetched_at=datetime.now(UTC),
                cursor=str(offset),
            )
            if next_offset is None:
                return
            offset = next_offset

    def _request_json(self, path: str, params: dict[str, str] | None = None) -> Any:
        request_params = {"api_token": self.config.api_token, "fmt": "json", **(params or {})}
        url = urljoin(str(self.config.base_url), path)
        for attempt in range(self.config.max_retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=request_params,
                    timeout=self.config.timeout,
                    allow_redirects=False,
                )
            except requests.RequestException as error:
                if attempt == self.config.max_retries:
                    raise RuntimeError(f"EODHD request failed: {error.__class__.__name__}") from None
                self._sleep(attempt, None)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == self.config.max_retries:
                    raise RuntimeError(f"EODHD request failed after retries with HTTP {response.status_code}")
                self._sleep(attempt, response.headers.get("Retry-After"))
                continue
            if response.status_code >= 300:
                raise RuntimeError(f"EODHD request failed with HTTP {response.status_code}")
            try:
                return response.json()
            except ValueError:
                raise RuntimeError("EODHD returned invalid JSON") from None
        raise AssertionError("unreachable")

    @staticmethod
    def _sleep(attempt: int, retry_after: str | None) -> None:
        """Wait for the provider's numeric or HTTP-date retry instruction."""
        fallback = min(2**attempt, 30)
        if not retry_after:
            time.sleep(fallback)
            return
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                delay = (parsedate_to_datetime(retry_after).astimezone(UTC) - datetime.now(UTC)).total_seconds()
            except (TypeError, ValueError):
                delay = fallback
        time.sleep(min(max(delay, 0), 60))

    @staticmethod
    def _extract_page(payload: Any, offset: int) -> tuple[list[dict[str, Any]], int | None]:
        """Flatten JSON:API attributes and calculate the next verified offset."""
        if not isinstance(payload, dict):
            raise RuntimeError("EODHD options response must be a JSON object")
        data, meta = payload.get("data"), payload.get("meta")
        if not isinstance(data, list) or not isinstance(meta, dict):
            raise RuntimeError("EODHD options response is missing data or meta")
        records: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("attributes"), dict):
                raise RuntimeError("EODHD options response contains an invalid data item")
            record = dict(item["attributes"])
            if isinstance(item.get("id"), str):
                record["source_record_id"] = item["id"]
            records.append(record)
        reported_offset, limit, total = meta.get("offset"), meta.get("limit"), meta.get("total")
        if (
            not isinstance(reported_offset, int)
            or reported_offset != offset
            or not isinstance(limit, int)
            or limit <= 0
            or (total is not None and (not isinstance(total, int) or total < offset))
        ):
            raise RuntimeError("EODHD options response contains invalid pagination metadata")
        next_offset = offset + len(records)
        if len(records) > limit:
            raise RuntimeError("EODHD options response has inconsistent pagination")
        if not records:
            return records, None
        if total is not None:
            return records, next_offset if next_offset < total else None
        return records, next_offset if len(records) == limit else None
