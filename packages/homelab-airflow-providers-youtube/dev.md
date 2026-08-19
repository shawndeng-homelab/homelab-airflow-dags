# YouTube Airflow Provider 开发说明

## 运行时基线

- Python 3.12。
- Apache Airflow 2.11.0。
- 使用 `airflow.datasets.Dataset` 和 `DatasetAlias`，不导入 Airflow 3 的 `airflow.sdk`。
- Provider 保持只读，不负责 YouTube 上传、OAuth 授权或业务游标持久化。
- 数据模型复用 `homelab-video-contracts`，不在 Provider 内复制。

## 职责

本 Provider 负责：

- 使用 YouTube Data API Key 查询公开频道。
- 读取频道 uploads playlist。
- 分页发现视频并批量补全元数据。
- 按半开时间窗口筛选上传视频。
- 提供 Hook、Operator、reschedule Sensor 和 Dataset Event。
- 返回适合 XCom 和动态任务映射的小型 JSON。

本 Provider 不负责：

- 运行 `yt-dlp` 或 FFmpeg。
- 保存 YouTube Cookie、PO Token 或账号密码。
- 写入 RustFS。
- ASR、翻译、TTS、渲染或 Bilibili 投稿。
- 使用 Airflow Variable 或历史 XCom 隐式保存 cursor。

下载由 Localization Service 的 `download` Job 完成。Cookie、下载代理、PO Token Provider 和 yt-dlp 配置属于服务内部 Secret。

## Provider 结构

当前规模使用扁平模块：

```text
src/homelab_airflow_providers_youtube/
├── __init__.py
├── datasets.py
├── events.py
├── get_provider_info.py
├── hooks.py
├── operators.py
├── sensors.py
└── py.typed
```

Provider entry point group 为 `apache_airflow_provider`，并声明 hooks、operators、sensors 和 connection-types。

## Connection

```text
Connection ID: youtube_default
Connection type: youtube
Password: YouTube Data API Key
Extra:
  api_base_url: https://www.googleapis.com/youtube/v3
  timeout: 30
  proxy: optional Data API proxy
  max_retries: 2
  retry_delay: 1
```

只读取公开数据，因此不需要 OAuth。API Key 不得出现在 DAG 参数、模板字段、异常、Dataset extra 或普通日志中。

## API 查询策略

频道上传发现不使用配额较高且语义不稳定的 `search.list`：

1. `channels.list(part=snippet,contentDetails)` 获取频道和 uploads playlist。
2. `playlistItems.list(part=contentDetails)` 分页读取视频 ID。
3. `videos.list(part=snippet,contentDetails)` 每批最多 50 个 ID，补全标题、发布时间、缩略图、语言和时长。
4. 按请求顺序去重并返回 `YouTubeVideo`。

公开结果最多返回 200 条，避免无限分页和过大的 XCom。时间窗口固定为：

```text
published_after <= published_at < published_before
```

所有时间必须带时区并在内部转换为 UTC。

## 重试与错误

- 连接错误、超时、HTTP 429 和 5xx 执行有限指数退避。
- 其他 4xx 不自动重试，避免重复消耗 quota。
- 错误只包含 HTTP 状态、YouTube reason 和有限长度的服务消息。
- 不拼接带 `key` 查询参数的 URL，也不透传 requests 原始异常 URL。
- `test_connection()` 使用最小只读查询，会消耗少量 quota。

## Dataset Event

稳定 URI：

```text
youtube://channel/{channel_id}/uploads
youtube://video/{video_id}
```

静态频道在 DAG 解析期声明 Dataset。模板化频道必须显式传入 `DatasetAlias`，运行时再绑定实际频道 Dataset。

只有发现视频时才产生事件。频道事件 extra 只保留：

- `video_count`
- 最多 50 个 `video_ids`
- `published_after`
- `published_before`

完整结果通过当前任务 XCom 返回，不写入 Dataset extra。

## Operator 与 Sensor

`YouTubeChannelVideosOperator`：

- 模板字段为频道 ID、时间窗口和 Connection ID。
- 返回 `list[dict]`。
- 静态频道自动声明 uploads Dataset。

`YouTubeChannelVideoSensor`：

- 默认 `mode='reschedule'`。
- 未命中返回未完成，不产生 Dataset Event。
- 命中后通过 `PokeReturnValue` 返回相同 JSON。

## 状态与幂等性

Provider 不维护 cursor。业务 DAG 应使用数据区间筛选，并在下游数据库或 Manifest 中对 `video_id` 建唯一约束。下载 Job 使用 `youtube:{video_id}` 等稳定幂等键。

补跑、并发 DagRun 和历史清理不会依赖上一个 TaskInstance 的 XCom。

## 测试要求

- Provider metadata 和 Connection type。
- API Key 缺失与配置映射。
- 频道到 uploads playlist 的转换。
- 视频补全、ISO 8601 时长和请求顺序。
- 多页查询与半开时间窗口边界。
- 非法 Dataset ID。
- API Key 不出现在错误中。
- Operator JSON、静态 Dataset 和动态 DatasetAlias。
- Sensor 未命中和命中行为。

HTTP 测试全部使用 mock，不访问真实 YouTube。

## 当前状态

- [x] Provider discovery。
- [x] `youtube` Connection 和 `YouTubeHook`。
- [x] 频道、播放列表、视频查询和分页。
- [x] Operator、reschedule Sensor、Dataset 和 DatasetAlias。
- [x] 共享 `YouTubeChannel`、`YouTubeVideo` 契约。
- [x] 单元测试和 README。
- [ ] Localization Service 实现真实 yt-dlp download Job。
- [ ] 下载视频、元数据、缩略图和原字幕写入 RustFS。
- [ ] 增加实际 DAG，并对 `video_id` 做外部幂等入库。
