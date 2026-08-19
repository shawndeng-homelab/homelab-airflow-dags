"""Local FFmpeg rendering and media-quality contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import Field
from pydantic import model_validator

from homelab_video_contracts.artifacts import Artifact
from homelab_video_contracts.base import ContractModel
from homelab_video_contracts.base import NonNegativeInt
from homelab_video_contracts.base import PositiveInt
from homelab_video_contracts.base import S3Uri
from homelab_video_contracts.base import VersionedContract


class AudioStrategy(StrEnum):
    """How localized speech is combined with the source audio."""

    SUBTITLE_ONLY = "subtitle_only"
    VOICE_OVERLAY = "voice_overlay"
    VOICE_REPLACE = "voice_replace"
    SILENT_BED = "silent_bed"


class VideoCodec(StrEnum):
    """Supported final video encoding modes."""

    COPY = "copy"
    LIBX264 = "libx264"


class RenderSettings(ContractModel):
    """Reproducible settings for a local FFmpeg render."""

    audio_strategy: AudioStrategy = AudioStrategy.SUBTITLE_ONLY
    burn_subtitles: bool = False
    video_codec: VideoCodec = VideoCodec.COPY
    preset: str = "fast"
    crf: Annotated[int, Field(ge=0, le=51)] = 22
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    pixel_format: str = "yuv420p"
    faststart: bool = True

    @model_validator(mode="after")
    def validate_encoding_mode(self) -> RenderSettings:
        """Prevent subtitle burning while copying the encoded video stream."""
        if self.burn_subtitles and self.video_codec is VideoCodec.COPY:
            raise ValueError("burned subtitles require video re-encoding")
        return self


class RenderRequest(VersionedContract):
    """Inputs and settings for the K8s FFmpeg render job."""

    source_video: Artifact
    output_uri: S3Uri
    settings: RenderSettings = Field(default_factory=RenderSettings)
    dubbed_audio: Artifact | None = None
    accompaniment_audio: Artifact | None = None
    subtitle_ass: Artifact | None = None

    @model_validator(mode="after")
    def validate_inputs(self) -> RenderRequest:
        """Require the media inputs implied by the selected render strategy."""
        if self.settings.burn_subtitles and self.subtitle_ass is None:
            raise ValueError("subtitle_ass is required when burn_subtitles is enabled")
        if (
            self.settings.audio_strategy
            in {
                AudioStrategy.VOICE_OVERLAY,
                AudioStrategy.VOICE_REPLACE,
                AudioStrategy.SILENT_BED,
            }
            and self.dubbed_audio is None
        ):
            raise ValueError("dubbed_audio is required for the selected audio strategy")
        if self.settings.audio_strategy is AudioStrategy.VOICE_REPLACE and self.accompaniment_audio is None:
            raise ValueError("voice_replace requires accompaniment_audio")
        return self


class RenderResult(VersionedContract):
    """A locally rendered video and its probe metadata."""

    video: Artifact
    duration_ms: PositiveInt
    width: PositiveInt
    height: PositiveInt
    video_codec: Annotated[str, Field(min_length=1)]
    audio_codec: Annotated[str, Field(min_length=1)]
    subtitle_burned: bool
    backend: str = "local_ffmpeg"


class MediaQualityCheck(ContractModel):
    """One named media validation outcome."""

    name: Annotated[str, Field(min_length=1)]
    passed: bool
    detail: str | None = None


class MediaQualityReport(VersionedContract):
    """Probe and policy results for a final media artifact."""

    video: Artifact
    passed: bool
    checks: tuple[MediaQualityCheck, ...]
    duration_delta_ms: NonNegativeInt | None = None
    integrated_loudness_lufs: float | None = None
