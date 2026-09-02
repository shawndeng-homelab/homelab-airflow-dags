"""Airflow operator for EODHD option EOD ingestion."""

from __future__ import annotations

from datetime import date
from typing import Any
from typing import ClassVar

from airflow.datasets import Dataset
from airflow.models import BaseOperator

from homelab_airflow_providers_financial_data.datasets import OPTIONS_EOD_QUOTES_DATASET
from homelab_airflow_providers_financial_data.hooks import EodhdHook
from homelab_airflow_providers_financial_data.ingestion import EodhdOptionsIngestion
from homelab_airflow_providers_financial_data.ingestion import new_storage_target
from homelab_airflow_providers_financial_data.models import EodhdOptionEodRequest
from homelab_airflow_providers_financial_data.storage import FinancialDataS3Store


class EodhdOptionsEodToS3Operator(BaseOperator):
    """Ingest EODHD option quotes and publish a compact XCom summary."""

    template_fields = ("underlying_symbol", "quote_date", "bucket", "prefix", "run_id")
    outlets: ClassVar[list[Dataset]] = [Dataset(OPTIONS_EOD_QUOTES_DATASET)]

    def __init__(
        self,
        *,
        underlying_symbol: str,
        quote_date: str | date,
        bucket: str,
        prefix: str = "financial-data",
        eodhd_conn_id: str = EodhdHook.default_conn_name,
        aws_conn_id: str = "aws_default",
        exchange: str = "US",
        replace: bool = False,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize an ingestion task with its source and S3 configuration."""
        super().__init__(**kwargs)
        self.underlying_symbol = underlying_symbol
        self.quote_date = quote_date
        self.bucket = bucket
        self.prefix = prefix
        self.eodhd_conn_id = eodhd_conn_id
        self.aws_conn_id = aws_conn_id
        self.exchange = exchange
        self.replace = replace
        self.run_id = run_id

    def execute(self, context: Any) -> dict[str, Any]:
        """Run the service and return only manifest metadata through XCom."""
        request = EodhdOptionEodRequest(
            underlying_symbol=self.underlying_symbol,
            quote_date=date.fromisoformat(str(self.quote_date)),
            exchange=self.exchange,
            replace=self.replace,
            run_id=self.run_id,
        )
        target = new_storage_target(self.bucket, self.prefix, self.run_id)
        manifest = EodhdOptionsIngestion(EodhdHook(self.eodhd_conn_id), FinancialDataS3Store(self.aws_conn_id)).run(
            request, target
        )
        return {
            "run_id": manifest.run_id,
            "quote_date": manifest.quote_date.isoformat(),
            "underlying_symbol": manifest.underlying_symbol,
            "curated_uris": [artifact.uri for artifact in manifest.curated_artifacts],
            "quality": manifest.quality_report.model_dump(mode="json"),
        }
