"""Immutable boundary and persistence models for financial-data ingestion."""

from __future__ import annotations

from datetime import UTC
from datetime import date
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import HttpUrl
from pydantic import model_validator


class ContractModel(BaseModel):
    """Strict, immutable model used at provider boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class EodhdConnectionConfig(ContractModel):
    """Resolved EODHD connection settings."""

    api_token: str = Field(min_length=1, repr=False)
    base_url: HttpUrl = "https://eodhd.com/api/"
    timeout: float = Field(default=30, gt=0, le=300)
    proxy: HttpUrl | None = None
    max_retries: int = Field(default=4, ge=0, le=10)
    page_limit: int = Field(default=1000, ge=1, le=1000)
    verify: bool = True


class EodhdOptionEodRequest(ContractModel):
    """A single underlying's EOD option-chain request."""

    underlying_symbol: str = Field(min_length=1, pattern=r"^[A-Za-z0-9.\-]+$")
    quote_date: date
    exchange: Literal["US"] = "US"
    replace: bool = False
    run_id: str | None = Field(default=None, min_length=1)

    @property
    def qualified_symbol(self) -> str:
        """Return the EODHD ticker qualified with its exchange."""
        return f"{self.underlying_symbol.upper()}.{self.exchange.upper()}"


class RawPage(ContractModel):
    """An exact EODHD response page retained for reproducibility."""

    page_number: int = Field(ge=1)
    records: tuple[dict[str, Any], ...]
    payload: Any
    fetched_at: datetime
    cursor: str | None = None

    @model_validator(mode="after")
    def check_fetched_at(self) -> RawPage:
        """Require the source observation timestamp to be UTC-aware."""
        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() != UTC.utcoffset(self.fetched_at):
            raise ValueError("fetched_at must be UTC-aware")
        return self


class StorageTarget(ContractModel):
    """Bucket and root prefix for an ingestion run."""

    bucket: str = Field(min_length=3)
    prefix: str = "financial-data"
    run_id: str = Field(min_length=1)

    @property
    def normalized_prefix(self) -> str:
        """Return the prefix with boundary slashes removed."""
        return self.prefix.strip("/")


class Artifact(ContractModel):
    """An immutable object persisted by a storage backend."""

    uri: str
    key: str
    content_type: str
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_at: datetime


class QualitySeverity(StrEnum):
    """Severity assigned to a data-quality finding."""

    WARNING = "warning"
    ERROR = "error"


class QualityIssue(ContractModel):
    """A non-fatal issue associated with one source record or rule."""

    code: str
    message: str
    severity: QualitySeverity = QualitySeverity.WARNING
    raw_page_number: int | None = Field(default=None, ge=1)
    raw_record_index: int | None = Field(default=None, ge=0)
    source_record_id: str | None = None


class QualityReport(ContractModel):
    """Summary of quality checks for the curated artifact."""

    input_records: int = Field(ge=0)
    accepted_records: int = Field(ge=0)
    rejected_records: int = Field(ge=0)
    duplicate_records: int = Field(default=0, ge=0)
    issues: tuple[QualityIssue, ...] = ()


class IngestionManifest(ContractModel):
    """The atomically published pointer to one successful curated version."""

    schema_version: Literal["2.0"] = "2.0"
    source: Literal["eodhd"] = "eodhd"
    dataset: Literal["options.eod_quotes"] = "options.eod_quotes"
    quote_date: date
    underlying_symbol: str
    run_id: str
    published_at: datetime
    raw_artifacts: tuple[Artifact, ...]
    curated_artifacts: tuple[Artifact, ...]
    quality_report: QualityReport


class ManifestPointer(ContractModel):
    """Small mutable pointer to one immutable ingestion manifest."""

    schema_version: Literal["2.0"] = "2.0"
    dataset: Literal["options.eod_quotes"] = "options.eod_quotes"
    quote_date: date
    underlying_symbol: str
    run_id: str
    manifest_uri: str
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_at: datetime


class OptionType(StrEnum):
    """US option contract right."""

    CALL = "call"
    PUT = "put"


class OptionEodQuote(ContractModel):
    """Semantic schema for one normalized option EOD quote."""

    schema_version: Literal["2.0"] = "2.0"
    source: Literal["eodhd"] = "eodhd"
    contract: str = Field(min_length=1)
    source_record_id: str | None = None
    raw_page_number: int = Field(ge=1)
    raw_record_index: int = Field(ge=0)
    underlying_symbol: str
    quote_date: date
    source_quote_time_raw: str | None = None
    source_trade_time_raw: str | None = None
    ingested_at: datetime
    expiration: date
    option_type: OptionType
    strike: Decimal = Field(ge=0)
    underlying_price: Decimal | None = Field(default=None, ge=0)
    open: Decimal | None = Field(default=None, ge=0)
    high: Decimal | None = Field(default=None, ge=0)
    low: Decimal | None = Field(default=None, ge=0)
    close: Decimal | None = Field(default=None, ge=0)
    bid: Decimal | None = Field(default=None, ge=0)
    ask: Decimal | None = Field(default=None, ge=0)
    volume: int | None = Field(default=None, ge=0)
    open_interest: int | None = Field(default=None, ge=0)
    implied_volatility: Decimal | None = Field(default=None, ge=0)
    delta: Decimal | None = None
    gamma: Decimal | None = Field(default=None, ge=0)
    theta: Decimal | None = None
    vega: Decimal | None = Field(default=None, ge=0)
    rho: Decimal | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    contract_multiplier: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_dates_and_time(self) -> OptionEodQuote:
        """Enforce the contract's date and ingestion-time invariants."""
        if self.expiration < self.quote_date:
            raise ValueError("expiration must be on or after quote_date")
        if self.ingested_at.tzinfo is None or self.ingested_at.utcoffset() != UTC.utcoffset(self.ingested_at):
            raise ValueError("ingested_at must be UTC-aware")
        return self
