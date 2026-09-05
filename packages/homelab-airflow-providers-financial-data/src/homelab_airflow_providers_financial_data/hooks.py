"""Airflow adapter for the Airflow-independent EODHD REST client."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import requests
from airflow.exceptions import AirflowException
from airflow.hooks.base import BaseHook
from pydantic import ValidationError

from homelab_airflow_providers_financial_data.client import EodhdClient
from homelab_airflow_providers_financial_data.models import EodhdConnectionConfig
from homelab_airflow_providers_financial_data.models import EodhdOptionEodRequest
from homelab_airflow_providers_financial_data.models import RawPage


class EodhdHook(BaseHook):
    """Resolve an Airflow connection and delegate requests to :class:`EodhdClient`."""

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
        except ValidationError:
            raise AirflowException("Invalid EODHD connection configuration") from None

    def get_conn(self) -> requests.Session:
        """Create a configured requests session for Airflow's standard hook contract."""
        return EodhdClient._new_session(self.get_connection_config())

    def test_connection(self) -> tuple[bool, str]:
        """Validate credentials using a read-only endpoint."""
        with EodhdClient(self.get_connection_config()) as client:
            return client.test_connection()

    def iter_option_eod_pages(self, request: EodhdOptionEodRequest) -> Iterator[RawPage]:
        """Yield Marketplace EOD pages, translating transport errors to Airflow errors."""
        try:
            with EodhdClient(self.get_connection_config()) as client:
                yield from client.iter_option_eod_pages(request)
        except RuntimeError as error:
            raise AirflowException(str(error)) from None
