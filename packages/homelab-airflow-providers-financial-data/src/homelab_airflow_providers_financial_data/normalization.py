"""Polars-based normalization and non-fatal quality checks."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import polars as pl

from homelab_airflow_providers_financial_data.models import QualityIssue
from homelab_airflow_providers_financial_data.models import QualityReport


class EodhdOptionNormalizer:
    """Map EODHD's flexible wire schema to a stable curated schema."""

    _decimal_columns = (
        "strike",
        "underlying_price",
        "open",
        "high",
        "low",
        "close",
        "bid",
        "ask",
        "implied_volatility",
        "delta",
        "gamma",
        "theta",
        "vega",
        "rho",
    )

    def __init__(self, quote_date: date, underlying_symbol: str) -> None:
        """Bind the source-independent partition values for this conversion."""
        self.quote_date = quote_date
        self.underlying_symbol = underlying_symbol.upper()

    def to_frame(self, records: Iterable[dict[str, Any]]) -> pl.DataFrame:
        """Materialize raw records once while retaining their input locations."""
        return pl.DataFrame(list(records), infer_schema_length=None).with_row_index("source_record_index")

    def normalize(self, frame: pl.LazyFrame) -> pl.LazyFrame:
        """Produce a typed, sorted LazyFrame without Python row iteration."""
        fields = set(frame.collect_schema().names())

        def field(*names: str) -> pl.Expr:
            for name in names:
                if name in fields:
                    return pl.col(name)
            return pl.lit(None)

        def coalesced_field(*names: str) -> pl.Expr:
            """Return the first non-null value among available upstream aliases."""
            available = [pl.col(name) for name in names if name in fields]
            return pl.coalesce(available) if available else pl.lit(None)

        expressions = [
            pl.lit("1.0").alias("schema_version"),
            pl.lit("eodhd").alias("source"),
            field("contract", "contract_name").cast(pl.String).alias("contract"),
            pl.lit(self.underlying_symbol).alias("underlying_symbol"),
            pl.lit(self.quote_date).cast(pl.Date).alias("quote_date"),
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
        }
        expressions.extend(
            field(*source).cast(pl.Decimal(20, 6), strict=False).alias(target) for target, source in aliases.items()
        )
        expressions.extend(
            [
                field("volume").cast(pl.Int64, strict=False).alias("volume"),
                field("openInterest", "open_interest", "oi").cast(pl.Int64, strict=False).alias("open_interest"),
                coalesced_field("lastTradeDateTime", "observed_at", "timestamp", "bid_date", "ask_date", "tradetime")
                .cast(pl.String)
                .str.to_datetime(strict=False, time_zone="UTC")
                .alias("observed_at"),
                pl.col("source_record_index"),
            ]
        )
        return (
            frame.select(expressions)
            .with_columns(pl.col("observed_at").fill_null(pl.lit(None, dtype=pl.Datetime(time_zone="UTC"))))
            .sort(["quote_date", "underlying_symbol", "expiration", "option_type", "strike"])
        )

    def validate(self, frame: pl.LazyFrame) -> QualityReport:
        """Report invalid records; callers filter them but retain valid quotes."""
        materialized = (
            frame.select(
                pl.len().alias("input_records"),
                (
                    (pl.col("contract").is_null())
                    | (pl.col("contract").str.len_chars() == 0)
                    | (pl.col("strike").is_null())
                    | (pl.col("strike") < 0)
                    | pl.col("expiration").is_null()
                    | (pl.col("expiration") < pl.col("quote_date"))
                    | ~pl.col("option_type").is_in(["call", "put"])
                    | pl.col("observed_at").is_null()
                )
                .sum()
                .alias("rejected_records"),
                ((pl.col("bid").is_not_null()) & (pl.col("ask").is_not_null()) & (pl.col("ask") < pl.col("bid")))
                .sum()
                .alias("crossed_quotes"),
            )
            .collect()
            .row(0, named=True)
        )
        rejected = int(materialized["rejected_records"] or 0)
        issues: list[QualityIssue] = []
        if rejected:
            issues.append(
                QualityIssue(
                    code="invalid_contract",
                    message=f"{rejected} records have invalid contract fields",
                    severity="error",
                )
            )
        crossed = int(materialized["crossed_quotes"] or 0)
        if crossed:
            issues.append(QualityIssue(code="crossed_market", message=f"{crossed} records have ask below bid"))
        total = int(materialized["input_records"])
        return QualityReport(
            input_records=total, accepted_records=total - rejected, rejected_records=rejected, issues=tuple(issues)
        )

    @staticmethod
    def valid_records(frame: pl.LazyFrame) -> pl.LazyFrame:
        """Keep valid contracts while allowing all quality findings to be persisted."""
        return frame.filter(
            pl.col("contract").is_not_null()
            & (pl.col("contract").str.len_chars() > 0)
            & pl.col("strike").is_not_null()
            & (pl.col("strike") >= 0)
            & pl.col("expiration").is_not_null()
            & (pl.col("expiration") >= pl.col("quote_date"))
            & pl.col("option_type").is_in(["call", "put"])
            & pl.col("observed_at").is_not_null()
        ).drop("source_record_index")
