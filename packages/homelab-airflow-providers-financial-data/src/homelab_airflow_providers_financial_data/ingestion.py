"""Application service coordinating one EODHD options ingestion run."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from uuid import uuid4

from homelab_airflow_providers_financial_data.hooks import EodhdHook
from homelab_airflow_providers_financial_data.models import EodhdOptionEodRequest
from homelab_airflow_providers_financial_data.models import IngestionManifest
from homelab_airflow_providers_financial_data.models import StorageTarget
from homelab_airflow_providers_financial_data.normalization import EodhdOptionNormalizer
from homelab_airflow_providers_financial_data.storage import FinancialDataS3Store
from homelab_airflow_providers_financial_data.storage import LocalFilesystemStore


class EodhdOptionsIngestion:
    """Run raw capture, curated conversion, and manifest-last publication."""

    def __init__(self, hook: EodhdHook, store: FinancialDataS3Store | LocalFilesystemStore) -> None:
        """Initialize the service with its source and storage dependencies."""
        self.hook = hook
        self.store = store

    def run(self, request: EodhdOptionEodRequest, target: StorageTarget) -> IngestionManifest:
        """Ingest one underlying and return its published (or existing) manifest."""
        symbol = request.underlying_symbol.upper()
        existing = self.store.load_current_manifest(target, request.quote_date.isoformat(), symbol)
        if existing and not request.replace:
            return existing

        raw_artifacts = []
        records = []
        for page in self.hook.iter_option_eod_pages(request):
            raw_artifacts.append(self.store.write_raw_page(page, target, request.quote_date.isoformat(), symbol))
            records.extend(page.records)

        normalizer = EodhdOptionNormalizer(request.quote_date, symbol)
        raw_frame = normalizer.to_frame(records)
        normalized = normalizer.normalize(raw_frame.lazy())
        report = normalizer.validate(normalized)
        curated = normalizer.valid_records(normalized)
        curated_artifacts = [self.store.write_parquet(curated, target, request.quote_date.isoformat(), symbol)]
        manifest = IngestionManifest(
            quote_date=request.quote_date,
            underlying_symbol=symbol,
            run_id=target.run_id,
            published_at=datetime.now(UTC),
            raw_artifacts=tuple(raw_artifacts),
            curated_artifacts=tuple(curated_artifacts),
            quality_report=report,
        )
        self.store.publish_manifest(manifest, target)
        return manifest


def new_storage_target(bucket: str, prefix: str, run_id: str | None = None) -> StorageTarget:
    """Create a collision-resistant S3 target for an operator invocation."""
    return StorageTarget(bucket=bucket, prefix=prefix, run_id=run_id or uuid4().hex)
