# Homelab Airflow Financial Data Provider

An Apache Airflow provider for immutable ingestion of financial market data. Version 1 ingests EODHD US option end-of-day data into S3 as raw JSON, curated Parquet, and a manifest-last publication record.

Create an `eodhd` Airflow connection with the API token in the password field. Optional connection extras are `base_url`, `timeout`, `proxy`, `max_retries`, and `verify`.
