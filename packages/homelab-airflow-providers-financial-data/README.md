# Homelab Airflow 金融数据 Provider

这是一个用于不可变采集金融市场数据的 Apache Airflow Provider。v1 只支持 EODHD 的美股期权日终（EOD）数据：保存完整原始响应、标准化 Parquet，以及最后发布的 manifest。

## 能做什么

`EodhdOptionsEodToS3Operator` 针对一个美股标的和一个交易日期采集期权 EOD 记录，并在一次成功运行中产出：

- 每页完整 API 响应的 gzip JSON（Raw）。
- 使用 Zstandard 压缩的标准化 Parquet（Curated）。
- `current.json` manifest，其中包含产物 URI、SHA-256、运行 ID 与数据质量报告。

manifest 是唯一的发布边界。下游先读取轻量的 `current.json` 指针，再读取它指向的不可变运行 manifest；不能仅通过某个 Raw 或 Parquet 文件存在来判断一批数据成功。

## 安装

本仓库使用 uv workspace 管理该包。独立 Airflow 环境可安装发布后的包：

```bash
pip install homelab-airflow-providers-financial-data
```

使用 Optopsy 适配器时，需要可选依赖：

```bash
pip install 'homelab-airflow-providers-financial-data[optopsy]'
```

## 配置 Airflow Connection

创建类型为 `eodhd` 的 Airflow Connection。默认连接 ID 是 `eodhd_default`，也可通过 Operator 参数传入其他 ID。

| 字段 | 配置值 |
| --- | --- |
| Connection type | `eodhd` |
| Password | EODHD API Token |
| Host / schema / login / port | 留空 |
| Extra | 可选 JSON，见下方示例 |

```json
{
  "base_url": "https://eodhd.com/api/",
  "timeout": 30,
  "max_retries": 4,
  "page_limit": 1000,
  "verify": true
}
```

需要代理时，可在 Extra 中加入 HTTPS URL：

```json
{"proxy": "https://proxy.example.com:8443"}
```

Hook 会重试网络异常、HTTP 429 与 5xx 响应，并在 `Retry-After` 是数值时遵守该等待时间。API Token 不会出现在 S3 key、manifest 或 Provider 抛出的异常文本中。

目标 S3 则通过普通 Amazon Provider Connection 配置，默认 ID 是 `aws_default`。

## 在 DAG 中使用

下面是使用方式示例，不会随 Provider 注册为生产 DAG：

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
        dataset_uri="s3://financial-data/curated/dataset=options.eod_quotes",
    )
```

Operator 的 XCom 有意保持很小，只返回运行 ID、请求日期、标的、Curated URI 与序列化质量报告。若需发布 Airflow Dataset event，请显式传入不含 Jinja 模板的稳定 `dataset_uri`；Dataset URI 在 DAG 解析时确定，不能安全地从运行时渲染的 `bucket` 或 `prefix` 推导：

```text
s3://financial-data/curated/dataset=options.eod_quotes
```

## 不使用 S3 的本地验证

可以。`LocalFilesystemStore` 复用了 Raw、Curated 和 manifest-last 的 key 布局与发布顺序，但写入本地目录。它专用于本地开发和集成验证；生产 DAG 的 Operator 始终使用 S3。

仓库提供了可直接运行的下载脚本。它不需要 Airflow scheduler、数据库、S3 或 MinIO：

```powershell
$env:EODHD_API_TOKEN = "your-token"
uv run python packages/homelab-airflow-providers-financial-data/examples/download_options_to_local.py `
  --symbol AAPL --quote-date 2025-01-02
```

默认写入 `.local-financial-data/local-bucket/financial-data/`。重复运行同一标的和日期时，默认复用已发布版本；需要重新下载并推进 `current.json` 指针时加 `--replace`。可通过 `--output-dir`、`--bucket`、`--prefix` 与 `--run-id` 调整本地布局。

若希望连同真实 EODHD API 一起试跑，可将 `EodhdClient` 与 `LocalFilesystemStore` 组合。这种方式不需要 Airflow、AWS 或 MinIO；只需设置 EODHD 的环境变量：

```powershell
$env:EODHD_API_TOKEN = "your-token"
# 可选：EODHD_BASE_URL、EODHD_TIMEOUT、EODHD_MAX_RETRIES、EODHD_PAGE_LIMIT
```

```python
from datetime import date
from pathlib import Path

from homelab_airflow_providers_financial_data.client import EodhdClient
from homelab_airflow_providers_financial_data.ingestion import EodhdOptionsIngestion, new_storage_target
from homelab_airflow_providers_financial_data.models import EodhdOptionEodRequest
from homelab_airflow_providers_financial_data.storage import LocalFilesystemStore

request = EodhdOptionEodRequest(underlying_symbol="SPY", quote_date=date(2025, 1, 2))
target = new_storage_target(bucket="local-bucket", prefix="financial-data")
store = LocalFilesystemStore(Path(".local-financial-data"))

with EodhdClient.from_environment() as client:
    manifest = EodhdOptionsIngestion(client, store).run(request, target)
print(manifest.curated_artifacts[0].uri)
```

上述代码会在以下位置写入文件：

```text
.local-financial-data/local-bucket/financial-data/...
```

完全离线时，可用 fixture source 替代 `EodhdClient`。只要对象实现 `iter_option_eod_pages(request)` 并返回 `RawPage`，`EodhdOptionsIngestion` 就能完成整个本地流程；这也是编写集成测试时推荐的方式。

```python
from datetime import UTC, date, datetime
from pathlib import Path

from homelab_airflow_providers_financial_data.ingestion import EodhdOptionsIngestion, new_storage_target
from homelab_airflow_providers_financial_data.models import EodhdOptionEodRequest, RawPage
from homelab_airflow_providers_financial_data.storage import LocalFilesystemStore


class FixtureHook:
    def iter_option_eod_pages(self, request):
        yield RawPage(
            page_number=1,
            cursor="0",
            fetched_at=datetime.now(UTC),
            payload={"fixture": True},
            records=(
                {
                    "contract": "AAPL250117C00200000",
                    "exp_date": "2025-01-17",
                    "type": "call",
                    "strike": 200,
                    "bid": 5.1,
                    "ask": 5.3,
                    "volume": 42,
                    "open_interest": 100,
                    "volatility": 0.25,
                    "bid_date": "2025-01-02 14:59:59",
                },
            ),
        )


request = EodhdOptionEodRequest(underlying_symbol="AAPL", quote_date=date(2025, 1, 2))
target = new_storage_target(bucket="local-bucket", prefix="financial-data", run_id="fixture-run")
manifest = EodhdOptionsIngestion(FixtureHook(), LocalFilesystemStore(Path(".local-financial-data"))).run(
    request, target
)
print(manifest.model_dump_json(indent=2))
```

## S3 对象布局与发布行为

```text
financial-data/
├── raw/source=eodhd/dataset=options.eod/ingestion_date=YYYY-MM-DD/
│   └── underlying_symbol=AAPL/run_id=<run-id>/page-00001.json.gz
├── curated/dataset=options.eod_quotes/schema_version=2.0/source=eodhd/
│   └── quote_date=YYYY-MM-DD/underlying_symbol=AAPL/run_id=<run-id>/part-00001.parquet
└── manifests/dataset=options.eod_quotes/schema_version=2.0/source=eodhd/
    └── quote_date=YYYY-MM-DD/underlying_symbol=AAPL/
        ├── current.json
        └── runs/<run-id>.json
```

Raw、Curated 与运行 manifest 的 key 都含有 `run_id`，因此不可变。所有 Raw 与 Curated 成功后才会写入运行 manifest，再通过条件写更新 `current.json`。同一标的和日期已有成功 manifest 时，默认跳过运行；设置 `replace=True` 会创建新的 `run_id` 并在成功后推进指针，不会删除旧版本。S3 使用 ETag 条件写；本地模式使用排他锁和原子替换，两个竞争运行不会静默覆盖彼此。

失败运行可能遗留用于排障的 Raw 页面，但绝不会修改 `current.json`。因此下游读者始终可以安全地使用已发布 manifest。

## Curated schema 与质量报告

Parquet 包含合约与行情字段，以及 `source_record_id`、`raw_page_number`、`raw_record_index`、原始时间字符串和 UTC `ingested_at`。其中 `quote_date` 表示请求的 EOD 分区，不冒充交易所行情时间。输出排序为：

```text
quote_date, underlying_symbol, expiration, option_type, strike
```

缺失合约号、无效 strike/日期/Call-Put 类型或缺少观测时间的记录，会从 Curated 文件排除，并在 manifest 的质量报告中记为 error。交叉报价（`ask < bid`）仍会保留给消费者，并记为 warning。

EODHD 的此 endpoint 使用 `tradetime` 过滤数据。它可能是最后成交时间；当没有成交时，也可能反映其他期权更新。因此应将 `quote_date` 理解为所请求的 EOD 分区，审计单条记录时以持久化的原始响应为准。

## 使用 manifest 消费 Polars 或 Optopsy

下游通过 `FinancialDataManifestReader` 解析当前指针，只扫描已经完整发布的 Curated 文件；不要直接扫描整个 Curated 前缀。

```python
from datetime import date
from pathlib import Path

from homelab_airflow_providers_financial_data.ingestion import new_storage_target
from homelab_airflow_providers_financial_data.readers import FinancialDataManifestReader
from homelab_airflow_providers_financial_data.storage import LocalFilesystemStore

target = new_storage_target(bucket="local-bucket", prefix="financial-data", run_id="reader")
reader = FinancialDataManifestReader(LocalFilesystemStore(Path(".local-financial-data")))
quotes = reader.scan_current_parquet(target, date(2025, 1, 2).isoformat(), "AAPL")
```

S3 消费者同样使用该 reader，但传入 `FinancialDataS3Store`，并让 Airflow AWS Connection 提供凭据。

```python
print(quotes.filter(pl.col("underlying_symbol") == "AAPL").collect())
```

Optopsy 适配器会先选择兼容列，再转换到 Pandas；它不会用 close 伪造 bid/ask：

```python
from homelab_airflow_providers_financial_data.integrations.optopsy import to_optopsy_frame

optopsy_input = to_optopsy_frame(quotes)
```
