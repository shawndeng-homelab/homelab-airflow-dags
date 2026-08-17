# YouTube Airflow Provider 开发计划

## 目标

将 `homelab-airflow-providers-youtube` 建设为面向 Apache Airflow 3 的轻量 Provider，第一阶段聚焦：

- 使用 API Key 访问 YouTube Data API 的公开数据。
- 查询频道上传的视频及其元数据。
- 通过 Operator 获取时间窗口内的新视频。
- 通过 Sensor 等待频道发布新视频。
- 使用 Airflow Asset 表达频道上传流和具体视频，并在发现新视频时产生 Asset Event。
- 将视频信息以适合 XCom 和动态任务映射的结构返回给业务 DAG。

典型工作流：

```text
定时触发 DAG
  -> 检查频道是否发布新视频
  -> 返回结构化视频信息
  -> 下游下载 / 入库 / 上传 MinIO / Bark 通知
```

Provider 只负责 YouTube 集成。下载、对象存储、数据库、通知以及业务游标由 `homelab-airflow-dags` 编排。

## 第一版范围

### 包含

- Airflow Provider discovery 元数据。
- `youtube` Connection 类型和 `youtube_default` 默认连接。
- 只读 `YouTubeHook`。
- 频道上传列表查询和分页。
- `YouTubeChannelVideosOperator`。
- `YouTubeChannelVideoSensor`。
- YouTube Asset URI 规范、辅助构造函数和 Asset Event 元数据。
- 结构化视频模型。
- 单元测试和使用文档。

### 暂不包含

- 视频上传和播放列表写操作。
- OAuth 浏览器授权流程。
- YouTube Analytics。
- `yt-dlp` 下载。
- MinIO、数据库和 Bark 等业务逻辑。
- Hook 内部持久化“上次处理位置”。
- Deferrable Sensor 和 Trigger。
- 自定义 Asset Watcher；第一版由定时 DAG、Operator 或 Sensor 产生 Asset Event。

## 推荐目录结构

```text
homelab-airflow-providers-youtube/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── dev.md
├── src/homelab_airflow_providers_youtube/
│   ├── __init__.py
│   ├── get_provider_info.py
│   ├── assets.py
│   ├── py.typed
│   ├── hooks/
│   │   ├── __init__.py
│   │   └── youtube.py
│   ├── sensors/
│   │   ├── __init__.py
│   │   └── youtube.py
│   ├── operators/
│   │   ├── __init__.py
│   │   └── youtube.py
│   └── models/
│       ├── __init__.py
│       └── video.py
└── tests/
    ├── conftest.py
    ├── test_provider_info.py
    ├── test_hook.py
    ├── test_sensor.py
    └── test_operator.py
```

## Provider 元数据

在 `pyproject.toml` 中注册 Airflow Provider entry point：

```toml
[project.entry-points."apache_airflow_provider"]
provider_info = "homelab_airflow_providers_youtube.get_provider_info:get_provider_info"
```

`get_provider_info()` 至少声明：

- `package-name`: `homelab-airflow-providers-youtube`
- `name`: `YouTube`
- `description`
- `connection-types`
- `hooks`
- `operators`
- `sensors`

Provider 绑定当前仓库的运行环境：

- Python `>=3.12,<3.13`
- Apache Airflow `==3.2.0`
- Airflow 基类优先从稳定公共接口 `airflow.sdk` 导入。

## Connection 设计

- Connection ID：`youtube_default`
- Connection type：`youtube`
- Password：YouTube Data API Key
- Extra：
  - `api_base_url`，默认 `https://www.googleapis.com/youtube/v3`
  - `timeout`
  - 可选代理配置

API Key 不应出现在 DAG 参数、普通日志、异常信息或明文示例中。第一版仅支持公开数据和 API Key；私有数据与写操作需要 OAuth 2.0，后续独立设计。YouTube Data API 不支持使用 Service Account 代表 YouTube 用户。

## Hook 设计

建议公开接口：

```python
class YouTubeHook(BaseHook):
    conn_name_attr = "youtube_conn_id"
    default_conn_name = "youtube_default"
    conn_type = "youtube"
    hook_name = "YouTube"

    def get_conn(self) -> YouTubeClient: ...
    def get_channel(self, channel_id: str) -> Channel: ...
    def get_uploads_playlist_id(self, channel_id: str) -> str: ...
    def list_playlist_videos(...) -> list[YouTubeVideo]: ...
    def list_channel_videos(...) -> list[YouTubeVideo]: ...
    def get_videos(self, video_ids: Sequence[str]) -> list[YouTubeVideo]: ...
```

实现建议：

- 使用 REST API 和 `requests.Session`。
- 不依赖完整的 `apache-airflow-providers-google` 或 Google Discovery Client。
- 处理分页并强制支持 `max_results` 上限。
- 解析 RFC 3339 时间。
- 使用明确的请求超时。
- 对 429 和 5xx 进行有限次数指数退避。
- 将 400、401、403、404 等响应转换为明确的 Airflow 异常。
- 使用 `fields` 参数减少响应体。
- 按 `video_id` 对结果去重。
- 本地验证参数，减少无效请求消耗配额。

## API 查询策略

获取频道上传记录时不使用 `search.list`，采用 YouTube 官方推荐流程：

1. 调用 `channels.list(part=contentDetails, id=...)`。
2. 获取 `relatedPlaylists.uploads`。
3. 调用 `playlistItems.list(part=snippet,contentDetails, playlistId=...)`。
4. 必要时批量调用 `videos.list` 补充时长、直播状态等字段。

该方案比搜索接口语义更准确，也能稳定分页。API 请求即使失败也可能消耗配额，因此需要本地参数校验和受控重试。

## 数据模型

Provider 应返回稳定的小模型，不直接把 Google 原始响应作为公共 API：

```python
@dataclass(frozen=True, slots=True)
class YouTubeVideo:
    video_id: str
    channel_id: str
    channel_title: str | None
    title: str
    description: str | None
    published_at: datetime
    thumbnail_url: str | None
    playlist_item_id: str | None

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"
```

Operator 和 Sensor 写入 XCom 时转换为 JSON-safe 的字典，时间使用标准 ISO 8601 字符串。

## Asset 设计

Asset 用来表达“哪个 YouTube 逻辑资源发生了更新”，不承担 API 查询、去重或业务 cursor 的职责。第一版定义两类稳定 URI：

```text
youtube://channel/{channel_id}/uploads
youtube://video/{video_id}
```

约束：

- URI 只使用 YouTube 不变 ID，不使用可能改名的频道标题、handle 或视频标题。
- URI scheme 和路径保持小写，YouTube ID 保留原始大小写。
- URI 中不包含 API Key、Connection ID、发布时间等环境或运行时信息。
- 同一个逻辑资源在不同 DAG 中必须生成完全相同的 URI。

在 `assets.py` 中提供集中构造函数，DAG 不手写 URI：

```python
def youtube_channel_uploads_asset(channel_id: str) -> Asset: ...
def youtube_video_asset(video_id: str) -> Asset: ...
```

### Asset Event 语义

发现一个或多个此前未处理的视频后：

- 频道 uploads Asset 表示该频道上传流出现了新内容。
- 需要按单个视频驱动下游时，为每个视频产生对应的视频 Asset Event。
- 没有发现新视频时不产生成功更新事件，避免无变化的轮询触发下游 DAG。
- API 查询成功不等于 Asset 更新；只有符合时间窗口或业务判定的新视频才算更新。

Asset Event 的 `extra` 使用精简、JSON-safe 的元数据：

```python
{
    "video_id": "...",
    "channel_id": "...",
    "published_at": "2026-08-17T12:00:00Z",
    "title": "...",
    "url": "https://www.youtube.com/watch?v=...",
}
```

完整 description、thumbnail 集合和 YouTube 原始响应不写入事件元数据，避免放大元数据库。大批量发现时，频道 Asset Event 只记录 `video_count`、时间窗口和有限的 `video_ids` 摘要；完整结果仍由 XCom、小型文件或外部存储传递。

### 与 Operator、Sensor 的关系

- `YouTubeChannelVideosOperator` 支持声明频道 uploads Asset 为 `outlets`；仅在匹配到视频时附加事件元数据。
- `YouTubeChannelVideoSensor` 命中时产生相同语义的事件，未命中、超时或 soft-fail 时不更新 Asset。
- 当 `channel_id` 在 DAG 解析期已知时，直接使用频道 Asset。
- 当频道或视频 ID 只能在运行时确定时，使用 Airflow 的动态 Asset/Alias 机制，避免在解析期伪造 URI。
- 下游 DAG 可以按频道 uploads Asset 调度，再从触发事件元数据或外部状态读取本批视频。

第一版不在 `get_provider_info()` 中注册自定义 Asset URI handler，也不实现主动监听 YouTube 的 Asset Watcher。`youtube://` URI 先作为本 Provider 的稳定命名契约；需要 URI 规范化、额外 lineage 集成或事件驱动 watcher 时再扩展 provider metadata。

## Operator 设计

`YouTubeChannelVideosOperator` 用于一次性获取时间窗口内的频道视频：

```python
YouTubeChannelVideosOperator(
    task_id="list_new_videos",
    channel_id="UC...",
    youtube_conn_id="youtube_default",
    published_after="{{ data_interval_start }}",
    published_before="{{ data_interval_end }}",
    max_results=50,
)
```

要求：

- `channel_id`、时间窗口和连接 ID 支持模板化。
- 返回 `list[dict]`。
- 限制最大结果数量，避免大响应进入 XCom。
- 不执行数据库写入或下游业务操作。
- 匹配到视频时能够为声明的 YouTube Asset outlet 写入精简事件元数据。

## Sensor 设计

`YouTubeChannelVideoSensor` 用于等待指定时间之后出现新视频：

```python
YouTubeChannelVideoSensor(
    task_id="wait_for_video",
    channel_id="UC...",
    published_after="{{ data_interval_start }}",
    youtube_conn_id="youtube_default",
    mode="reschedule",
    poke_interval=300,
    timeout=3600,
)
```

要求：

- 默认推荐 `mode="reschedule"`，避免等待期间持续占用 Celery worker。
- 命中时通过 `PokeReturnValue` 将视频列表写入 XCom。
- 支持 `soft_fail` 等 `BaseSensorOperator` 标准行为。
- 第一版不实现 deferrable trigger；频道数量或并发明显增加后再评估。
- 只有命中新视频时才产生 Asset Event。

## 状态与幂等性

Provider 不读写 Airflow Variable，也不隐式维护 cursor。

推荐业务 DAG 使用以下方案之一：

- 使用 `data_interval_start` 和 `data_interval_end` 作为发布时间窗口。
- 在下游数据库对 `video_id` 建立唯一键并执行 upsert。
- 对严格游标场景，由业务 DAG 从外部数据库读取和提交 cursor。

时间过滤采用半开区间：

```text
published_after <= published_at < published_before
```

不依赖“上一个 TaskInstance 的 XCom”保存状态，以免补跑、历史清理或并发 DagRun 破坏一致性。

## 测试计划

- Provider entry point 和 `get_provider_info()` schema。
- Connection UI 字段和默认 Connection ID。
- API Key 缺失行为。
- channel 到 uploads playlist 的解析。
- playlist 单页和多页查询。
- 时间窗口过滤和边界值。
- API 响应缺失可选字段。
- 400、401、403、404、429 和 5xx 错误处理。
- API Key 不出现在日志和异常中。
- Operator 模板字段及 JSON-safe 返回值。
- Sensor 未命中、命中、soft fail 和 XCom 返回值。
- Asset URI 构造、ID 校验和稳定性。
- Operator/Sensor 仅在发现新视频时产生 Asset Event。
- Asset Event `extra` 可 JSON 序列化且不包含凭据和过大的原始响应。
- 静态频道 Asset 与运行时动态视频 Asset/Alias 行为。
- DAG import test。

所有 HTTP 测试使用 mock，不访问真实 YouTube，不消耗 API 配额。

## 实施阶段

### 1. Provider 基础设施

- 补齐项目元数据、MIT License、README 和 CHANGELOG。
- 注册 `apache_airflow_provider` entry point。
- 实现 `get_provider_info()`。
- 添加 Provider discovery 测试。

### 2. 只读 Hook

- 实现 API Key Connection。
- 实现 HTTP client、频道上传列表和分页。
- 实现异常映射和结构化数据模型。
- 完成 Hook 单元测试。

### 3. Airflow 组件

- 实现 `YouTubeChannelVideosOperator`。
- 实现 `YouTubeChannelVideoSensor`。
- 支持模板字段、时间窗口和 XCom。
- 实现 YouTube Asset 构造函数和 URI 规范。
- 为 Operator/Sensor 添加 Asset outlet 和事件元数据。
- 完成 Operator 和 Sensor 测试。

### 4. DAG 集成

- 在 `homelab-airflow-dags` 中增加实际或示例 DAG。
- 串接 YouTube 查询、下游处理和 Bark 通知。
- 增加由频道 uploads Asset 调度的下游 DAG 示例。
- 业务 cursor 保留在 DAG 或外部数据库层。

### 5. 运行环境与发布

- Dockerfile 同时安装 DAG 包和 YouTube Provider。
- 更新 workspace README 包列表。
- 调整测试覆盖率命令，确保 Provider 被单独统计。
- 执行 `just lint`、`just test-all` 和 `just build`。
- 在 Linux 容器或 CI 中使用 `airflow providers list` 验证 discovery。

### 6. 后续可选能力

- 基于 YouTube Feed 的无 API Key 监听。
- 自定义 Asset Watcher、URI handler 和更完整的 lineage 集成。
- Deferrable Sensor 和 Trigger。
- OAuth 用户授权。
- 视频上传和播放列表管理。
- 字幕相关能力。
- 将 `yt-dlp` 下载设计为独立可选 extra/operator。

## 当前仓库待办

- 当前包仍是最小脚手架，`__init__.py` 中只有 `hello()`。
- `cog.toml` 同时存在正确的 `homelab-airflow-providers-youtube` 和不存在的旧项 `homelab-providers-youtube`，实施时删除旧项。
- `cog.toml` 已引用本包的 `CHANGELOG.md`，但该文件尚不存在。
- Dockerfile 当前只安装 `homelab-airflow-dags`，不会安装新 Provider。
- 根 README 的 workspace 包列表尚未包含本 Provider。
- 当前测试命令的 coverage 目标固定为 DAG 包，可能遗漏 Provider 覆盖率。
- Windows 原生环境运行 Airflow CLI 会因 `fcntl` 缺失失败，最终 discovery 验证应放在 Linux 容器或 CI。

## v0.1.0 完成标准

v0.1.0 定义为：API Key、公开频道读取、结构化视频模型、查询 Operator、`reschedule` Sensor、YouTube Asset URI 与事件支持、完整 mock 测试以及可被 Airflow 正确发现的 Provider 包。
