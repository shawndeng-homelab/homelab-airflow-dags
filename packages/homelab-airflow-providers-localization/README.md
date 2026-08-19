# Homelab Airflow Providers Localization

Apache Airflow 2.11 Provider，用于向 Localization Gateway 提交和等待视频本地化作业。

执行边界：

- Airflow 只负责编排、幂等键和作业状态。
- 外部服务负责 ASR、翻译、TTS 和可选人声分离。
- 独立 K8s CPU Job 负责 FFmpeg 预处理、混音和最终字幕压制。
- RustFS 保存不可变输入、输出和 Manifest。
- Airflow worker 不运行模型，也不执行长时间 FFmpeg 任务。

Provider 与 Gateway 共享 homelab-video-contracts，不在 Provider 内重复定义 Job 模型。

## Connection

    Connection ID: localization_default
    Connection type: localization
    Host: https://localization.example.internal
    Password: optional Gateway bearer token
    Extra:
      timeout: 30
      verify_tls: true

外部 ASR、翻译和 TTS 厂商凭据由 Gateway 管理，不拆成 Airflow Connection。

## Operators

- VideoDownloadOperator
- AudioTranscriptionOperator
- SubtitleTranslationOperator
- SourceSeparationOperator
- SpeechSynthesisOperator
- VideoRenderOperator
- LocalizationJobOperator

SourceSeparationOperator 只在 voice_replace 模式下需要。subtitle_only 和 voice_overlay 可以跳过。

    from homelab_airflow_providers_localization.operators import VideoDownloadOperator

    download = VideoDownloadOperator(
        task_id='download',
        input_uri='https://www.youtube.com/watch?v={{ params.video_id }}',
        output_prefix='s3://video-localization/youtube/{{ params.video_id }}/source',
        parameters={
            'format': 'bestvideo+bestaudio',
        },
        localization_conn_id='localization_default',
    )

Operator 默认使用 deferrable 模式。远程作业运行期间，LocalizationJobTrigger 在 triggerer 中异步轮询，不占用 worker slot。

## 统一 Job API

提交：

    POST /v1/jobs
    Idempotency-Key: <dag_id>:<run_id>:<task_id>:<map_index>

请求体：

    schema_version: 1.0
    job_type: transcribe
    input_uri: s3://video-localization/youtube/abc/audio/speech.flac
    output_prefix: s3://video-localization/youtube/abc/asr
    parameters:
      provider: external-asr
      model: whisper-large-v3

查询：

    GET /v1/jobs/{job_id}

取消：

    POST /v1/jobs/{job_id}/cancel

健康检查：

    GET /health

状态只能是：

    queued
    running
    succeeded
    failed
    cancelled

失败响应必须包含结构化错误：

    schema_version: 1.0
    job_id: job-123
    job_type: transcribe
    status: failed
    error:
      schema_version: 1.0
      code: provider_rate_limited
      message: External ASR returned HTTP 429
      retryable: true

响应只返回 Job 状态、小型 JSON 数据和稳定的 s3:// URI。禁止通过 XCom 或 Job API 返回 base64 音视频。

## 本地 FFmpeg

VideoRenderOperator 仍提交统一 render_video Job。Gateway 根据参数将它派发给 K8s CPU worker：

    job_type: render_video
    parameters:
      backend: local_ffmpeg
      burn_subtitles: true
      video_codec: libx264
      preset: fast
      crf: 22

只替换音频或封装软字幕时可以使用 video codec copy。烧录字幕时必须使用 libx264 等编码器，并将混音和烧录合并为一次最终编码。

## 凭据和数据

- Gateway bearer token 只存放在 localization_default Connection Password。
- 外部厂商密钥只存放在 Gateway Secret。
- Airflow XCom 只传小型 Job 字典和 s3:// URI。
- presigned URL 不进入 Job contract、XCom 或普通日志。
- 每次提交都应使用稳定 Idempotency-Key。
