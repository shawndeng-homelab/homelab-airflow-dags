# Homelab Airflow Financial Data Provider

An Apache Airflow provider for immutable ingestion of financial market data. Version 1 ingests EODHD US option end-of-day data into S3 as raw JSON, curated Parquet, and a manifest-last publication record.

Create an `eodhd` Airflow connection with the API token in the password field. Optional connection extras are `base_url`, `timeout`, `proxy`, `max_retries`, `page_limit`, and `verify`.

Raw and curated objects are immutable because their S3 keys include the run ID. The provider writes `current.json` only after raw and curated artifacts have succeeded. A later run skips a successful manifest by default; pass `replace=True` to publish a new version without deleting the prior one.

## Non-production example

The following is an example only. It is intentionally not packaged or registered as a production DAG.

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
        eodhd_conn_id="eodhd_default",
        aws_conn_id="aws_default",
    )
```
