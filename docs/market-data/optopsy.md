# Optopsy PostgreSQL 数据采集

`optopsy_market_data` 在每个 XNYS 交易日纽约时间 19:00 运行。它为每个配置标的分别下载期权链和股票 OHLCV 数据，并由 Optopsy 直接增量写入 PostgreSQL。

## 前置条件

在目标 PostgreSQL 实例中创建独立的 `optopsy` 数据库和最小权限用户。Optopsy 首次写入时会自动创建 `options_data` 和 `stocks_data` 表及其索引。

在 Airflow 中配置以下 Connections：

| Connection ID | 类型 | 必填字段 | 用途 |
| --- | --- | --- | --- |
| `optopsy_postgres` | PostgreSQL | host、schema、login、password、port | Optopsy 数据库；不能使用 Airflow metadata 库。 |
| `eodhd_default` | 任意已注册的 Connection 类型 | password | EODHD API key，仅用于期权数据。 |

配置 Airflow Variable `optopsy_market_symbols` 为非空 JSON 列表，例如：

```json
["SPY", "AAPL", "TSLA"]
```

标的会自动去空格、转为大写并去重。缺少该 Variable 或值无效时，任务会失败而不是下载隐式默认标的。

## 运行行为与排障

- 休市日会跳过，不向上游请求数据。
- 每个标的拆为独立的期权和股票任务，最多两个任务并行；失败任务自动重试两次，间隔十分钟。
- 每次 CLI 调用都带 `-v`，可从 Airflow task log 回溯 Optopsy 的请求窗口、增量状态和错误信息。
- 凭据通过子进程环境变量传递，不会出现在任务命令或 XCom 中；Optopsy 会脱敏其 EODHD token 日志。
- 首次期权下载会拉取可用历史，可能耗时较长；后续使用 PostgreSQL 中已有数据进行增量同步。

可以手动触发 DAG 以完成首次初始化。不要同时对相同标的手动触发多个 DAG run；虽然数据库写入为 upsert，重复的上游下载会浪费 EODHD 配额。
