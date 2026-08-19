# homelab-airflow-providers-youtube

面向 Apache Airflow 2.11 的只读 YouTube Provider，用于发现公开频道、查询上传视频、生成 Dataset Event，并把小型、版本化的视频元数据传给下游任务。

## 职责边界

```text
YouTube Data API
  -> YouTubeHook
  -> Operator / reschedule Sensor
  -> YouTubeVideo JSON
  -> Localization Service 的 VideoDownloadOperator
  -> RustFS
```

本 Provider 不运行 `yt-dlp`，也不保存 YouTube 登录态。实际下载由 Localization Service 完成，因此 Cookie、下载代理和 PO Token Provider 都保留在该服务的 K8s Secret 或只读 Secret 卷中。

## 能力

- 标准 Airflow Provider discovery。
- `youtube` Connection type 和 `youtube_default` 默认连接。
- `YouTubeHook` 频道、上传播放列表和视频元数据查询。
- 播放列表分页和最多 200 条结果的显式限制。
- `published_after <= published_at < published_before` 半开时间窗口。
- 视频 ID 去重、批量 `videos.list` 补全和 ISO 8601 时长解析。
- 对连接错误、超时、HTTP 429 和 5xx 的有限指数退避。
- API Key 脱敏的 Airflow 错误映射。
- `YouTubeChannelVideosOperator` 和默认 `reschedule` 的 `YouTubeChannelVideoSensor`。
- 静态 Dataset 与运行时 `DatasetAlias` 事件。
- 与 `homelab-video-contracts` 共享 `YouTubeChannel` 和 `YouTubeVideo`。

## 安装

```bash
uv add homelab-airflow-providers-youtube
```

仓库开发环境：

```bash
uv sync --all-packages --all-groups
```

## Connection

在 Airflow UI 中创建：

| 字段 | 值 |
| --- | --- |
| Connection ID | `youtube_default` |
| Connection type | `youtube` |
| Password | YouTube Data API v3 API Key |
| Extra: `api_base_url` | 默认 `https://www.googleapis.com/youtube/v3` |
| Extra: `timeout` | 默认 `30` 秒 |
| Extra: `proxy` | 可选，仅作用于 Data API 请求 |
| Extra: `max_retries` | 默认 `2`，允许 `0..5` |
| Extra: `retry_delay` | 默认 `1` 秒 |

公开频道、播放列表和视频元数据不需要 OAuth。应在 Google Cloud 中启用 YouTube Data API v3，并对 API Key 设置 API 限制；如果集群出口 IP 固定，也建议增加 IP 限制。

不要在 DAG 参数、XCom、Dataset extra 或日志中传递 API Key。

### 下载服务的登录信息

普通公开视频通常不需要 YouTube 登录。确实需要登录态时：

- 不保存 YouTube 用户名和密码。
- 使用专用低权限账号导出的 Netscape Cookie 文件。
- Cookie 文件通过 K8s Secret 只读挂载到 Localization Service。
- Airflow 只持有 `localization_default` 的服务 Bearer Token。
- PO Token 由下载服务中的 yt-dlp Provider 插件按需生成，不作为长期 Airflow Secret。
- 下载服务的代理和 Cookie 路径不复用本 Connection 的 Data API `proxy`。

账号 Cookie 只用于年龄限制、私人或会员内容，并应控制请求频率。账号存在被 YouTube 限制或封禁的风险。

## Hook

```python
from homelab_airflow_providers_youtube.hooks import YouTubeHook

hook = YouTubeHook(youtube_conn_id='youtube_default')

# 配置可以保留可读的 @handle；查询后得到永久 UC... ID。
channel = hook.get_channel_by_handle('@channel_handle')
videos = hook.list_channel_videos(
    channel.channel_id,
    published_after='2026-08-18T00:00:00Z',
    published_before='2026-08-19T00:00:00Z',
    max_results=50,
)
```

公开方法：

- `get_channel(channel_id)`
- `get_channel_by_handle(handle)`
- `get_uploads_playlist_id(channel_id)`
- `get_videos(video_ids)`
- `list_playlist_videos(playlist_id, ...)`
- `list_channel_videos(channel_id, ...)`
- `test_connection()`

`test_connection()` 会执行一次最小只读 Data API 请求，因此会消耗少量 API quota。

## Operator

```python
from homelab_airflow_providers_youtube.operators import YouTubeChannelVideosOperator

discover = YouTubeChannelVideosOperator(
    task_id='discover_channel_videos',
    channel_id='UC...',
    published_after='{{ data_interval_start }}',
    published_before='{{ data_interval_end }}',
    max_results=50,
)
```

返回值是 `list[dict]`，时间和 URL 已转换为 JSON-safe 字符串，可用于 XCom 和动态任务映射。不会返回 Google 原始响应。

静态 `channel_id` 会自动声明：

```text
youtube://channel/{channel_id}/uploads
```

只有发现至少一个视频时才更新 Dataset Event。事件只包含视频数量、最多 50 个视频 ID 和查询窗口。

## Sensor

```python
from homelab_airflow_providers_youtube.sensors import YouTubeChannelVideoSensor

wait_for_video = YouTubeChannelVideoSensor(
    task_id='wait_for_video',
    channel_id='UC...',
    published_after='{{ data_interval_start }}',
    poke_interval=300,
    timeout=3600,
)
```

Sensor 默认使用 `mode='reschedule'`，等待时不会持续占用 Worker slot。命中后通过 `PokeReturnValue` 返回视频列表并产生相同的 Dataset Event；未命中不会产生事件。

## 运行时频道与 DatasetAlias

模板化频道 ID 无法在 DAG 解析期建立静态 Dataset。此时显式传入 Alias：

```python
from airflow.datasets import DatasetAlias
from homelab_airflow_providers_youtube.operators import YouTubeChannelVideosOperator

discover = YouTubeChannelVideosOperator(
    task_id='discover_runtime_channel',
    channel_id='{{ params.channel_id }}',
    outlet=DatasetAlias('youtube-runtime-channel'),
)
```

运行时会通过 Alias 发出实际的 `youtube://channel/{channel_id}/uploads` Dataset。

## 接入远程下载

发现结果交给 Localization Provider 的 `VideoDownloadOperator`。推荐先用 TaskFlow 任务生成下载参数，再动态映射：

```python
from airflow.decorators import task
from homelab_airflow_providers_localization.operators.localization import VideoDownloadOperator


@task
def build_download_jobs(videos: list[dict]) -> list[dict]:
    return [
        {
            'input_uri': video['source_url'],
            'output_prefix': 's3://video-localization/source/{video_id}'.format(video_id=video['video_id']),
            'idempotency_key': 'youtube:{video_id}'.format(video_id=video['video_id']),
        }
        for video in videos
    ]


VideoDownloadOperator.partial(
    task_id='download_to_rustfs',
    localization_conn_id='localization_default',
).expand_kwargs(build_download_jobs(discover.output))
```

下载服务必须将视频、元数据、缩略图和原字幕写入 RustFS，并在 Job 输出中只返回 Artifact URI 和校验信息。

## Dataset URI

```python
from homelab_airflow_providers_youtube.datasets import youtube_channel_uploads_dataset
from homelab_airflow_providers_youtube.datasets import youtube_video_dataset

uploads = youtube_channel_uploads_dataset('UC...')
video = youtube_video_dataset('dQw4w9WgXcQ')
```

URI 只包含不可变 YouTube ID，不包含标题、Connection ID、API Key 或运行时间。

## 测试

```bash
uv run --package homelab-airflow-providers-youtube \
  pytest packages/homelab-airflow-providers-youtube/tests
```

所有 HTTP 测试均使用 mock，不访问真实 YouTube，也不消耗 API quota。
