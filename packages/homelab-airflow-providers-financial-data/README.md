# Homelab Airflow Financial Data Provider

An Apache Airflow provider for immutable ingestion of financial market data. Version 1 ingests EODHD US option end-of-day data into S3 as raw JSON, curated Parquet, and a manifest-last publication record.

## What it provides

`EodhdOptionsEodToS3Operator` collects one US underlying's option EOD records for a requested date. Each successful run writes:

- Original API responses as gzipped JSON, page by page.
- A normalized, Zstandard-compressed Parquet file.
- A `current.json` manifest containing artifact checksums, locations, and quality findings.

The manifest is the publication boundary: consumers should read the manifest first, never infer success merely from the presence of Raw or Parquet objects.

## Install

Within this repository, `uv` discovers the package as a workspace member. For a standalone Airflow environment, install the published package together with the Amazon provider:

```bash
pip install homelab-airflow-providers-financial-data
```

The optional Optopsy adapter needs Pandas and Optopsy:

```bash
pip install 'homelab-airflow-providers-financial-data[optopsy]'
```

## Configure connections

Create an Airflow connection with type `eodhd` and ID `eodhd_default` (or pass another ID to the operator).

| Field | Value |
| --- | --- |
| Connection type | `eodhd` |
| Password | Your EODHD API token |
| Host / schema / login / port | Leave blank |
| Extra | Optional JSON configuration below |

```json
{
  "base_url": "https://eodhd.com/api/",
  "timeout": 30,
  "max_retries": 4,
  "page_limit": 1000,
  "verify": true
}
```

`proxy` can be added as an HTTPS URL. The hook retries connection errors, HTTP 429, and 5xx responses; it honours a numeric `Retry-After` header. API tokens are never incorporated into S3 keys, manifests, or raised error messages.

Configure the target S3 credentials through a normal Amazon provider connection, defaulting to `aws_default`.

## Use from a DAG

This is an example only. It is intentionally not packaged or registered as a production DAG.

```python
from datetime import datetime

from airflow import DAG
from homelab_airflow_providers_financial_data.operators import EodhdOptionsEodToS3Operator

with DAG(
    dag_id="example_eodhd_options_eod_to_s3",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example", "financial-data"],
) as dag:
    EodhdOptionsEodToS3Operator(
        task_id="ingest_aapl",
        underlying_symbol="AAPL",
        quote_date="{{ ds }}",
        bucket="your-financial-data-bucket",
        prefix="financial-data",
        eodhd_conn_id="eodhd_default",
        aws_conn_id="aws_default",
    )
```

The operator returns a deliberately small XCom payload: run ID, requested quote date, underlying, curated artifact URIs, and the serialized quality report. It also emits an Airflow Dataset event at:

```text
s3://<bucket>/<prefix>/curated/dataset=options.eod_quotes
```

## Run without an operator

Models, normalization, quality checks, and storage have no Airflow task-context dependency. They can be composed in an application or an integration test:

```python
from datetime import date

from homelab_airflow_providers_financial_data.hooks import EodhdHook
from homelab_airflow_providers_financial_data.ingestion import EodhdOptionsIngestion, new_storage_target
from homelab_airflow_providers_financial_data.models import EodhdOptionEodRequest
from homelab_airflow_providers_financial_data.storage import FinancialDataS3Store

request = EodhdOptionEodRequest(underlying_symbol="SPY", quote_date=date(2025, 1, 2))
target = new_storage_target(bucket="your-financial-data-bucket", prefix="financial-data")
manifest = EodhdOptionsIngestion(EodhdHook("eodhd_default"), FinancialDataS3Store("aws_default")).run(
    request, target
)
print(manifest.curated_artifacts[0].uri)
```

## S3 layout and publication behavior

```text
financial-data/
├── raw/source=eodhd/dataset=options.eod/ingestion_date=YYYY-MM-DD/
│   └── underlying_symbol=AAPL/run_id=<run-id>/page-00001.json.gz
├── curated/dataset=options.eod_quotes/schema_version=1.0/source=eodhd/
│   └── quote_date=YYYY-MM-DD/underlying_symbol=AAPL/run_id=<run-id>/part-00001.parquet
└── manifests/dataset=options.eod_quotes/source=eodhd/
    └── quote_date=YYYY-MM-DD/underlying_symbol=AAPL/current.json
```

Raw and curated objects are immutable because their S3 keys include the run ID. The provider writes `current.json` only after raw and curated artifacts have succeeded. A later run skips a successful manifest by default; pass `replace=True` to publish a new version without deleting the prior one.

Failed runs can leave diagnostic Raw pages, but never update `current.json`. This makes an existing manifest safe for downstream readers while allowing source-response debugging.

## Curated schema and quality findings

The Parquet schema includes `contract`, `underlying_symbol`, `quote_date`, `expiration`, `option_type`, `strike`, OHLC, bid/ask, volume, open interest, IV, the five Greeks, and UTC `observed_at`. It is sorted by:

```text
quote_date, underlying_symbol, expiration, option_type, strike
```

Malformed contracts (missing contract, invalid strike/date/right, or missing observation time) are excluded from the curated file and counted as errors in the manifest quality report. Crossed markets (`ask < bid`) remain available to consumers and are reported as warnings.

EODHD uses `tradetime` to filter this endpoint. It can represent a last trade or, when no trade exists, another option update. Treat `quote_date` as the requested EOD partition and inspect the persisted API response when auditing an individual quote.

## Read with Polars or Optopsy

```python
import polars as pl

quotes = pl.scan_parquet("s3://your-financial-data-bucket/financial-data/curated/**/*.parquet")
print(quotes.filter(pl.col("underlying_symbol") == "AAPL").collect())
```

For Optopsy, pass the curated lazy frame to the adapter. It selects only compatible columns before converting to Pandas, and never fabricates bid/ask from a close price:

```python
from homelab_airflow_providers_financial_data.integrations.optopsy import to_optopsy_frame

optopsy_input = to_optopsy_frame(quotes)
```
