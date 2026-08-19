# homelab-video-contracts

YouTube 视频本地化流程的共享、版本化数据契约。

该包只依赖 Pydantic，不依赖 Airflow、boto3、HTTP 客户端、FFmpeg 或任何推理库，可以同时安装在：

- Airflow Provider
- Localization Gateway
- 外部 ASR、翻译和 TTS adapter
- K8s FFmpeg worker
- 审核和发布服务

## 设计规则

- 独立持久化的模型包含 schema_version。
- 当前 schema_version 为 1.0。
- 未声明字段一律拒绝，避免服务之间静默漂移。
- 持久化模型不可变。
- 时间轴统一使用整数毫秒。
- 所有时间戳必须带时区。
- RustFS 产物只保存稳定的 s3:// URI。
- presigned URL 不属于持久化契约。
- segment_id 在 ASR、翻译、字幕、TTS 和人工审核中保持稳定。
- Manifest 是产物索引，不是任务锁。

## 模块

| 模块 | 主要模型 |
| --- | --- |
| artifacts.py | Artifact |
| jobs.py | LocalizationJobRequest、LocalizationJob、JobError、JobType、JobStatus |
| youtube.py | YouTubeVideo |
| transcript.py | Transcript、TranscriptSegment、TranscriptWord |
| translation.py | TranslatedTimeline、TranslatedSegment |
| synthesis.py | SynthesisResult、SynthesizedSegment、SourceSeparationResult |
| rendering.py | RenderRequest、RenderSettings、RenderResult、MediaQualityReport |
| bilibili.py | BilibiliPublishResult |
| manifest.py | VideoManifest、StageRecord |

## Artifact

    from homelab_video_contracts import Artifact

    video = Artifact(
        uri='s3://video-localization/youtube/abc/source/video.mp4',
        content_type='video/mp4',
        size=123456,
        etag='etag-value',
        version_id='version-id',
        sha256='a' * 64,
    )

Artifact URI 必须包含 bucket 和 object key。HTTP URL、缺少 key 的 bucket URI，以及带查询参数的 presigned URL 都会被拒绝。

## Localization Job

Gateway 接收统一作业请求：

    from homelab_video_contracts import JobType
    from homelab_video_contracts import LocalizationJobRequest

    request = LocalizationJobRequest(
        job_type=JobType.TRANSCRIBE,
        input_uri='s3://video-localization/youtube/abc/audio/speech.flac',
        output_prefix='s3://video-localization/youtube/abc/asr',
        parameters={
            'provider': 'external-asr',
            'model': 'whisper-large-v3',
            'language': 'en',
        },
    )

标准状态：

    queued
    running
    succeeded
    failed
    cancelled

failed 状态必须携带结构化 JobError：

    from homelab_video_contracts import JobError
    from homelab_video_contracts import JobStatus
    from homelab_video_contracts import LocalizationJob

    job = LocalizationJob(
        job_id='job-123',
        job_type=JobType.TRANSCRIBE,
        status=JobStatus.FAILED,
        error=JobError(
            code='provider_rate_limited',
            message='External ASR returned HTTP 429',
            retryable=True,
        ),
    )

## ASR 与翻译时间轴

    from homelab_video_contracts import TranscriptSegment
    from homelab_video_contracts import TranscriptWord
    from homelab_video_contracts import TranslatedSegment

    transcript_segment = TranscriptSegment(
        segment_id='seg-0001',
        start_ms=1000,
        end_ms=2400,
        text='Hello world',
        words=(
            TranscriptWord(
                start_ms=1000,
                end_ms=1500,
                text='Hello',
                probability=0.99,
            ),
        ),
    )

    translated_segment = TranslatedSegment(
        segment_id='seg-0001',
        source_start_ms=1000,
        source_end_ms=2400,
        source_text='Hello world',
        translated_text='你好，世界',
        translation_version=1,
    )

局部重新翻译或重新配音时递增 translation_version，但不改变 segment_id。

## 外部 AI 与本地 FFmpeg

ASR、翻译、TTS 和可选人声分离由外部服务完成。最终混音、软字幕封装或字幕烧录由 K8s FFmpeg Job 完成。

只替换音频或者封装软字幕时可以复制视频流：

    from homelab_video_contracts.rendering import RenderSettings
    from homelab_video_contracts.rendering import VideoCodec

    settings = RenderSettings(
        video_codec=VideoCodec.COPY,
        burn_subtitles=False,
    )

烧录字幕必须重新编码：

    settings = RenderSettings(
        video_codec=VideoCodec.LIBX264,
        burn_subtitles=True,
        preset='fast',
        crf=22,
    )

RenderRequest 会检查：

- 字幕烧录必须提供 ASS Artifact。
- 字幕烧录不能使用 video codec copy。
- voice overlay 必须提供 dubbed audio。
- voice replace 必须同时提供 dubbed audio 和 accompaniment audio。

## Manifest

VideoManifest 记录一个 YouTube 视频当前可验证的产物和阶段状态：

    from datetime import UTC
    from datetime import datetime

    from homelab_video_contracts import JobStatus
    from homelab_video_contracts import StageRecord
    from homelab_video_contracts import VideoManifest

    timestamp = datetime.now(UTC)

    stage = StageRecord(
        job_type=JobType.DOWNLOAD,
        status=JobStatus.SUCCEEDED,
        job_id='download-job-1',
        idempotency_key='youtube:abc:download:v1',
        output_artifacts=('source.video',),
        parameters_sha256='b' * 64,
        started_at=timestamp,
        completed_at=timestamp,
    )

    manifest = VideoManifest(
        video_id='abc',
        source=youtube_video,
        artifacts={
            'source.video': video,
        },
        stages={
            JobType.DOWNLOAD: stage,
        },
        created_at=timestamp,
        updated_at=timestamp,
    )

Manifest 会拒绝不存在的 Artifact 引用、视频 ID 不一致、阶段类型不一致和倒序时间戳。

## JSON round trip

    payload = manifest.model_dump_json(indent=2)
    restored = VideoManifest.model_validate_json(payload)

    assert restored == manifest

## Schema 演进

- 向后兼容地新增可选字段时保持 1.x。
- 删除字段、改变语义或收紧已有字段时发布新的 major schema version。
- 服务读取未知 schema version 时必须失败，不能猜测。
- 对象存储中的旧 Manifest 不原地覆盖，使用 RustFS Version ID 保留历史。
