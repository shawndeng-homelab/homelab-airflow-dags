"""Tests for local FFmpeg render contracts."""

import pytest
from homelab_video_contracts.artifacts import Artifact
from homelab_video_contracts.rendering import AudioStrategy
from homelab_video_contracts.rendering import RenderRequest
from homelab_video_contracts.rendering import RenderSettings
from homelab_video_contracts.rendering import VideoCodec
from pydantic import ValidationError


def test_burned_subtitles_require_video_reencoding() -> None:
    """Reject an impossible stream-copy and subtitle-burn combination."""
    with pytest.raises(ValidationError, match="video re-encoding"):
        RenderSettings(burn_subtitles=True, video_codec=VideoCodec.COPY)


def test_burned_subtitles_require_ass_artifact(artifact: Artifact) -> None:
    """Require a concrete ASS input for libass rendering."""
    with pytest.raises(ValidationError, match="subtitle_ass"):
        RenderRequest(
            source_video=artifact,
            output_uri="s3://bucket/render/final.mp4",
            settings=RenderSettings(burn_subtitles=True, video_codec=VideoCodec.LIBX264),
        )


def test_voice_replace_requires_dub_and_accompaniment(artifact: Artifact) -> None:
    """Require both external TTS and separated background audio."""
    settings = RenderSettings(audio_strategy=AudioStrategy.VOICE_REPLACE, video_codec=VideoCodec.COPY)
    with pytest.raises(ValidationError, match="dubbed_audio"):
        RenderRequest(
            source_video=artifact,
            output_uri="s3://bucket/render/final.mp4",
            settings=settings,
        )

    dubbed = artifact.model_copy(update={"uri": "s3://bucket/tts/dubbed.wav", "content_type": "audio/wav"})
    with pytest.raises(ValidationError, match="accompaniment_audio"):
        RenderRequest(
            source_video=artifact,
            output_uri="s3://bucket/render/final.mp4",
            settings=settings,
            dubbed_audio=dubbed,
        )


def test_local_ffmpeg_request_supports_single_final_encode(artifact: Artifact) -> None:
    """Describe one render that mixes audio and burns subtitles together."""
    request = RenderRequest(
        source_video=artifact,
        output_uri="s3://bucket/render/final.mp4",
        settings=RenderSettings(
            audio_strategy=AudioStrategy.VOICE_OVERLAY,
            burn_subtitles=True,
            video_codec=VideoCodec.LIBX264,
            preset="fast",
            crf=22,
        ),
        dubbed_audio=artifact.model_copy(update={"uri": "s3://bucket/tts/dubbed.wav"}),
        subtitle_ass=artifact.model_copy(update={"uri": "s3://bucket/subtitle.zh-CN.ass"}),
    )

    assert request.settings.video_codec is VideoCodec.LIBX264
    assert request.settings.burn_subtitles is True
