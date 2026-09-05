"""Polars normalization, contract validation, and duplicate detection."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import polars as pl

from homelab_airflow_providers_financial_data.models import QualityIssue
from homelab_airflow_providers_financial_data.models import QualityReport


class EodhdOptionNormalizer:
    """Map EODHD records to the versioned curated options schema."""

    _key_columns = ("source", "contract", "quote_date")
    _nonnegative_decimal_columns = (
        "underlying_price",
        "open",
        "high",
        "low",
        "close",
        "bid",
        "ask",
        "implied_volatility",
    )
    _comparison_columns = (
        "underlying_symbol",
        "source_quote_time_raw",
        "source_trade_time_raw",
        "expiration",
        "option_type",
        "strike",
        "underlying_price",
        "open",
        "high",
        "low",
        "close",
        "bid",
        "ask",
        "volume",
        "open_interest",
        "implied_volatility",
        "delta",
        "gamma",
        "theta",
        "vega",
        "rho",
        "currency",
        "contract_multiplier",
    )

    def __init__(self, requested_quote_date: date, underlying_symbol: str) -> None:
        """Bind the requested partition for this conversion."""
        self.requested_quote_date = requested_quote_date
        self.underlying_symbol = underlying_symbol.upper()

    def to_frame(self, records: Iterable[dict[str, Any]]) -> pl.DataFrame:
        """Materialize records once without iterating them in the hot path."""
        return pl.DataFrame(list(records), infer_schema_length=None)

    def normalize(self, frame: pl.LazyFrame) -> pl.LazyFrame:
        """Produce one typed row per source record, including raw provenance."""
        fields = set(frame.collect_schema().names())

        def field(*names: str) -> pl.Expr:
            for name in names:
                if name in fields:
                    return pl.col(name)
            return pl.lit(None)

        def coalesced(*names: str) -> pl.Expr:
            available = [pl.col(name) for name in names if name in fields]
            return pl.coalesce(available) if available else pl.lit(None)

        expressions = [
            pl.lit("2.0").alias("schema_version"),
            pl.lit("eodhd").alias("source"),
            field("contract", "contract_name").cast(pl.String).alias("contract"),
            field("_source_record_id", "source_record_id").cast(pl.String).alias("source_record_id"),
            field("_raw_page_number").cast(pl.UInt32, strict=False).alias("raw_page_number"),
            field("_raw_record_index").cast(pl.UInt32, strict=False).alias("raw_record_index"),
            coalesced("underlying_symbol", "underlyingSymbol")
            .cast(pl.String)
            .str.to_uppercase()
            .fill_null(self.underlying_symbol)
            .alias("underlying_symbol"),
            field("tradetime", "trade_date").cast(pl.String).str.to_date(strict=False).alias("quote_date"),
            coalesced("bid_date", "ask_date", "lastTradeDateTime", "observed_at", "timestamp")
            .cast(pl.String)
            .alias("source_quote_time_raw"),
            field("tradetime", "trade_date").cast(pl.String).alias("source_trade_time_raw"),
            field("_ingested_at").cast(pl.Datetime(time_zone="UTC"), strict=False).alias("ingested_at"),
            field("expirationDate", "expiration", "expiry", "exp_date")
            .cast(pl.String)
            .str.to_date(strict=False)
            .alias("expiration"),
            field("type", "optionType", "option_type").cast(pl.String).str.to_lowercase().alias("option_type"),
            field("strike").cast(pl.Decimal(20, 6), strict=False).alias("strike"),
            field("underlyingPrice", "underlying_price")
            .cast(pl.Decimal(20, 6), strict=False)
            .alias("underlying_price"),
        ]
        aliases = {
            "open": ("open",),
            "high": ("high",),
            "low": ("low",),
            "close": ("close", "last"),
            "bid": ("bid",),
            "ask": ("ask",),
            "implied_volatility": ("impliedVolatility", "iv", "implied_volatility", "volatility"),
            "delta": ("delta",),
            "gamma": ("gamma",),
            "theta": ("theta",),
            "vega": ("vega",),
            "rho": ("rho",),
            "contract_multiplier": ("contract_multiplier", "multiplier"),
        }
        expressions.extend(
            field(*source).cast(pl.Decimal(20, 6), strict=False).alias(target) for target, source in aliases.items()
        )
        expressions.extend(
            [
                field("volume").cast(pl.Int64, strict=False).alias("volume"),
                field("openInterest", "open_interest", "oi").cast(pl.Int64, strict=False).alias("open_interest"),
                field("currency").cast(pl.String).str.to_uppercase().alias("currency"),
            ]
        )
        return frame.select(expressions).sort(
            ["quote_date", "underlying_symbol", "expiration", "option_type", "strike", "contract"]
        )

    def invalid_condition(self) -> pl.Expr:
        """Return the single validity predicate used for reporting and filtering."""
        invalid = (
            pl.col("contract").is_null()
            | (pl.col("contract").str.len_chars() == 0)
            | pl.col("raw_page_number").is_null()
            | pl.col("raw_record_index").is_null()
            | pl.col("quote_date").is_null()
            | (pl.col("quote_date") != pl.lit(self.requested_quote_date))
            | pl.col("expiration").is_null()
            | (pl.col("expiration") < pl.col("quote_date"))
            | pl.col("option_type").is_null()
            | ~pl.col("option_type").is_in(["call", "put"])
            | pl.col("strike").is_null()
            | (pl.col("strike") < 0)
            | pl.col("ingested_at").is_null()
            | (pl.col("underlying_symbol") != pl.lit(self.underlying_symbol))
        )
        for column in self._nonnegative_decimal_columns:
            invalid |= pl.col(column).is_not_null() & (pl.col(column) < 0)
        invalid |= pl.col("contract_multiplier").is_not_null() & (pl.col("contract_multiplier") <= 0)
        invalid |= pl.col("volume").is_not_null() & (pl.col("volume") < 0)
        invalid |= pl.col("open_interest").is_not_null() & (pl.col("open_interest") < 0)
        return invalid.fill_null(True)

    def validate(self, frame: pl.LazyFrame) -> QualityReport:
        """Summarize invalid, duplicate, and crossed-market records."""
        valid = frame.filter(~self.invalid_condition())
        summary = (
            frame.select(pl.len().alias("input_records"), self.invalid_condition().sum().alias("rejected_records"))
            .join(
                valid.select(
                    pl.len().alias("valid_records"),
                    ((pl.col("bid").is_not_null()) & (pl.col("ask").is_not_null()) & (pl.col("ask") < pl.col("bid")))
                    .sum()
                    .alias("crossed_quotes"),
                ),
                how="cross",
            )
            .join(self.deduplicate(valid).select(pl.len().alias("accepted_records")), how="cross")
            .collect()
            .row(0, named=True)
        )
        rejected = int(summary["rejected_records"] or 0)
        duplicate_records = int(summary["valid_records"] or 0) - int(summary["accepted_records"] or 0)
        issues: list[QualityIssue] = []
        if rejected:
            issues.append(
                QualityIssue(
                    code="invalid_contract",
                    message=f"{rejected} records violate the curated contract",
                    severity="error",
                )
            )
        if duplicate_records:
            issues.append(
                QualityIssue(
                    code="duplicate_contract",
                    message=f"{duplicate_records} duplicate records were removed",
                )
            )
        crossed = int(summary["crossed_quotes"] or 0)
        if crossed:
            issues.append(QualityIssue(code="crossed_market", message=f"{crossed} records have ask below bid"))
        return QualityReport(
            input_records=int(summary["input_records"]),
            accepted_records=int(summary["accepted_records"]),
            rejected_records=rejected,
            duplicate_records=duplicate_records,
            issues=tuple(issues),
        )

    def ensure_no_conflicting_duplicates(self, frame: pl.LazyFrame) -> None:
        """Reject duplicate logical keys whose market values disagree."""
        uniqueness_checks = [pl.col(column).n_unique().alias(column) for column in self._comparison_columns]
        field_conflict = pl.any_horizontal(*(pl.col(column) > 1 for column in self._comparison_columns))
        conflicts = (
            frame.filter(~self.invalid_condition())
            .group_by(*self._key_columns)
            .agg(pl.len().alias("records"), *uniqueness_checks)
            .filter((pl.col("records") > 1) & field_conflict)
            .select(*self._key_columns)
            .limit(5)
            .collect()
        )
        if conflicts.height:
            keys = conflicts.rows()
            raise ValueError(f"Conflicting duplicate option records for keys: {keys}")

    def valid_records(self, frame: pl.LazyFrame) -> pl.LazyFrame:
        """Filter invalid rows and retain a deterministic record per logical key."""
        return self.deduplicate(frame.filter(~self.invalid_condition()))

    def deduplicate(self, frame: pl.LazyFrame) -> pl.LazyFrame:
        """Retain the first sorted record for each logical key."""
        return frame.unique(subset=list(self._key_columns), keep="first", maintain_order=True)
