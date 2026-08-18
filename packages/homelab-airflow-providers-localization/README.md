# Homelab Airflow Providers Localization

Apache Airflow 2.11 Provider，用于把视频下载、外部语音识别、字幕翻译、可选人声分离、中文语音合成和视频渲染提交给独立的 Localization Service。

Airflow 只保存作业 ID 和 RustFS 的 `s3://` 对象键，不在 worker 内运行模型或 FFmpeg。Operator 默认使用 deferrable 模式，远程作业运行期间不占用 worker slot。

## Connection

- Connection ID：`localization_default`
- Connection type：`localization`
- Host：服务根地址，例如 `https://localization.example.internal`
- Password：可选 Bearer token
- Extra：包含 `timeout: 30` 和 `verify_tls: true`

Localization Service 内部持有 Groq、翻译服务、VoxCPM2 等凭据；这些凭据不拆成 Airflow Connection。

## Operators

- `VideoDownloadOperator`
- `AudioTranscriptionOperator`
- `SubtitleTranslationOperator`
- `SourceSeparationOperator`
- `SpeechSynthesisOperator`
- `VideoRenderOperator`
- `LocalizationJobOperator`：提交服务支持的自定义作业类型

人声分离只在 `voice_replace` 模式下需要。只有字幕，或者允许压低原声后叠加中文配音时，可以不创建 `SourceSeparationOperator`。

```python
from homelab_airflow_providers_localization.operators import VideoDownloadOperator

download = VideoDownloadOperator(
    task_id='download',
    input_uri='https://www.youtube.com/watch?v={{ params.video_id }}',
    output_prefix='s3://video-localization/jobs/{{ run_id }}/source',
    parameters={'format': 'bestvideo+bestaudio'},
    localization_conn_id='localization_default',
)
```

## Service contract

提交作业：

```text
POST /v1/jobs
Idempotency-Key: <dag_id>:<run_id>:<task_id>:<map_index>
```

请求体包含 `job_type`、`input_uri`、`output_prefix` 和 `parameters`。查询作业：

```text
GET /v1/jobs/{job_id}
```

响应至少包含：

```yaml
job_id: job-123
job_type: transcribe
status: queued
output: null
error: null
```

状态只能是 `queued`、`running`、`succeeded`、`failed` 或 `cancelled`。`output` 中返回 RustFS `s3://` URI，禁止返回大文件内容。

健康检查使用 `GET /health`。
