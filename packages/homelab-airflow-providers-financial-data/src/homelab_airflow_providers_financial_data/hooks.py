"""EODHD REST hook with safe retry and pagination behavior."""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import requests
from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook
from pydantic import ValidationError

from homelab_airflow_providers_financial_data.models import EodhdConnectionConfig
from homelab_airflow_providers_financial_data.models import EodhdOptionEodRequest
from homelab_airflow_providers_financial_data.models import RawPage


class EodhdHook(BaseHook):
    """Fetch EODHD responses without exposing its token in errors or logs."""

    conn_name_attr = "eodhd_conn_id"
    default_conn_name = "eodhd_default"
    conn_type = "eodhd"
    hook_name = "EOD Historical Data"

    def __init__(self, eodhd_conn_id: str = default_conn_name) -> None:
        """Initialize the hook with an Airflow connection ID."""
        super().__init__()
        self.eodhd_conn_id = eodhd_conn_id

    @classmethod
    def get_ui_field_behaviour(cls) -> dict[str, Any]:
        """Describe the EODHD connection form in the Airflow UI."""
        return {
            "hidden_fields": ["host", "schema", "login", "port"],
            "relabeling": {"password": "API token"},
            "placeholders": {"extra": '{"timeout": 30, "proxy": "https://proxy.example"}'},
        }

    def get_connection_config(self) -> EodhdConnectionConfig:
        """Resolve the connection and strictly validate non-secret extras."""
        connection = self.get_connection(self.eodhd_conn_id)
        try:
            return EodhdConnectionConfig(api_token=connection.password or "", **connection.extra_dejson)
        except ValidationError as error:
            raise AirflowException("Invalid EODHD connection configuration") from error

    def get_conn(self) -> requests.Session:
        """Create a configured, token-free session object."""
        config = self.get_connection_config()
        session = requests.Session()
        session.headers.update({"Accept": "application/json", "User-Agent": "homelab-airflow-financial-data/0.1"})
        if config.proxy:
            session.proxies.update({"http": str(config.proxy), "https": str(config.proxy)})
        session.verify = config.verify
        return session

    def test_connection(self) -> tuple[bool, str]:
        """Validate credentials using a read-only endpoint."""
        try:
            self._request_json("user/")
        except AirflowException as error:
            return False, str(error)
        return True, "EODHD credentials were accepted"

    def iter_option_eod_pages(self, request: EodhdOptionEodRequest) -> Iterator[RawPage]:
        """Yield Marketplace EOD pages, rejecting malformed pagination metadata."""
        config = self.get_connection_config()
        offset = 0
        page_number = 0
        while True:
            params: dict[str, str] = {
                "filter[underlying_symbol]": request.underlying_symbol.upper(),
                "filter[tradetime_from]": request.quote_date.isoformat(),
                "filter[tradetime_to]": request.quote_date.isoformat(),
                "page[offset]": str(offset),
                "page[limit]": str(config.page_limit),
                "sort": "exp_date,strike",
                "fmt": "json",
            }
            payload = self._request_json("mp/unicornbay/options/eod", params)
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
        config = self.get_connection_config()
        request_params = {"api_token": config.api_token, "fmt": "json", **(params or {})}
        url = urljoin(str(config.base_url), path)
        session = self.get_conn()
        for attempt in range(config.max_retries + 1):
            try:
                response = session.get(url, params=request_params, timeout=config.timeout)
            except requests.RequestException as error:
                if attempt == config.max_retries:
                    raise AirflowException(f"EODHD request failed: {error.__class__.__name__}") from error
                self._sleep(attempt, None)
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt == config.max_retries:
                    raise AirflowException(f"EODHD request failed after retries with HTTP {response.status_code}")
                self._sleep(attempt, response.headers.get("Retry-After"))
                continue
            if response.status_code >= 400:
                raise AirflowException(f"EODHD request failed with HTTP {response.status_code}")
            try:
                return response.json()
            except ValueError as error:
                raise AirflowException("EODHD returned invalid JSON") from error
        raise AssertionError("unreachable")

    @staticmethod
    def _sleep(attempt: int, retry_after: str | None) -> None:
        try:
            delay = min(float(retry_after), 60) if retry_after else min(2**attempt, 30)
        except ValueError:
            delay = min(2**attempt, 30)
        time.sleep(delay)

    @staticmethod
    def _extract_page(payload: Any, offset: int) -> tuple[list[dict[str, Any]], int | None]:
        """Flatten JSON:API attributes and calculate the next safe page offset."""
        if not isinstance(payload, dict):
            raise AirflowException("EODHD options response must be a JSON object")
        data, meta = payload.get("data"), payload.get("meta")
        if not isinstance(data, list) or not isinstance(meta, dict):
            raise AirflowException("EODHD options response is missing data or meta")
        records: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict) or not isinstance(item.get("attributes"), dict):
                raise AirflowException("EODHD options response contains an invalid data item")
            record = dict(item["attributes"])
            if isinstance(item.get("id"), str):
                record["source_record_id"] = item["id"]
            records.append(record)
        reported_offset, limit, total = meta.get("offset"), meta.get("limit"), meta.get("total")
        if (
            not isinstance(reported_offset, int)
            or reported_offset != offset
            or not isinstance(limit, int)
            or not isinstance(total, int)
            or limit <= 0
            or total < offset
        ):
            raise AirflowException("EODHD options response contains invalid pagination metadata")
        next_offset = offset + len(records)
        if len(records) > limit or (next_offset < total and not records):
            raise AirflowException("EODHD options response has inconsistent pagination")
        return records, next_offset if next_offset < total else None
