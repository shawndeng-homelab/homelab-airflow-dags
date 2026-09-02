"""Explicit optional adapter from curated Polars quotes to Optopsy inputs."""

from __future__ import annotations

import polars as pl


def to_optopsy_frame(frame: pl.LazyFrame):
    """Return the minimal Pandas shape required by Optopsy without inventing quotes.

    The optional dependency is imported only when this adapter is used.  `close`
    remains independent from bid/ask and is deliberately not synthesized.
    """
    try:
        import pandas as pd  # noqa: PLC0415
    except ImportError as error:  # pragma: no cover - environment dependent
        raise ImportError("Install the 'optopsy' extra to use the Optopsy adapter") from error
    del pd  # imported for an actionable dependency error and Polars conversion support
    columns = [
        "underlying_symbol",
        "quote_date",
        "expiration",
        "option_type",
        "strike",
        "bid",
        "ask",
        "close",
        "underlying_price",
        "volume",
        "open_interest",
    ]
    schema = frame.collect_schema()
    missing = sorted(set(columns) - set(schema.names()))
    if missing:
        raise ValueError(f"Curated frame is missing Optopsy columns: {', '.join(missing)}")
    return frame.select(columns).collect().to_pandas()
