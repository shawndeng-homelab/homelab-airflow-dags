"""Tests for ASR, translation, and synthesis timelines."""

import pytest
from homelab_video_contracts.artifacts import Artifact
from homelab_video_contracts.synthesis import SynthesisResult
from homelab_video_contracts.synthesis import SynthesizedSegment
from homelab_video_contracts.transcript import Transcript
from homelab_video_contracts.transcript import TranscriptSegment
from homelab_video_contracts.transcript import TranscriptWord
from homelab_video_contracts.translation import TranslatedSegment
from homelab_video_contracts.translation import TranslatedTimeline
from pydantic import ValidationError


def test_transcript_preserves_stable_segment_and_word_timestamps(artifact: Artifact) -> None:
    """Represent external ASR output on the absolute source timeline."""
    transcript = Transcript(
        source_audio=artifact.model_copy(update={"content_type": "audio/flac"}),
        language="en",
        duration_ms=60000,
        provider="external-asr",
        model="whisper-large-v3",
        segments=(
            TranscriptSegment(
                segment_id="seg-0001",
                start_ms=1000,
                end_ms=2400,
                text="Hello world",
                words=(
                    TranscriptWord(start_ms=1000, end_ms=1500, text="Hello", probability=0.99),
                    TranscriptWord(start_ms=1600, end_ms=2300, text="world", probability=0.98),
                ),
            ),
        ),
    )

    restored = Transcript.model_validate_json(transcript.model_dump_json())
    assert restored.segments[0].segment_id == "seg-0001"
    assert restored.segments[0].words[1].start_ms == 1600


def test_transcript_rejects_duplicate_segment_ids(artifact: Artifact) -> None:
    """Prevent ambiguous review and partial rerun targets."""
    segment = TranscriptSegment(segment_id="seg-0001", start_ms=0, end_ms=1000, text="Hello")
    with pytest.raises(ValidationError, match="segment_id must be unique"):
        Transcript(
            source_audio=artifact,
            language="en",
            duration_ms=60000,
            provider="external-asr",
            model="whisper-large-v3",
            segments=(segment, segment.model_copy(update={"start_ms": 2000, "end_ms": 3000})),
        )


def test_translated_timeline_and_tts_share_segment_id(artifact: Artifact) -> None:
    """Use one stable segment ID across translation, subtitles, and TTS."""
    translated = TranslatedTimeline(
        source_transcript=artifact.model_copy(update={"content_type": "application/json"}),
        source_language="en",
        target_language="zh-CN",
        provider="external-llm",
        model="translation-model",
        segments=(
            TranslatedSegment(
                segment_id="seg-0001",
                source_start_ms=1000,
                source_end_ms=2400,
                source_text="Hello world",
                translated_text="你好，世界",
            ),
        ),
    )
    synthesis = SynthesisResult(
        source_timeline=artifact.model_copy(update={"uri": "s3://bucket/timeline.json"}),
        language="zh-CN",
        provider="external-tts",
        model="tts-model",
        voice="female-1",
        segments=(
            SynthesizedSegment(
                segment_id="seg-0001",
                target_start_ms=1000,
                target_end_ms=2400,
                text="你好，世界",
                voice="female-1",
                audio=artifact.model_copy(update={"uri": "s3://bucket/tts/seg-0001.wav"}),
                actual_duration_ms=1300,
            ),
        ),
        dubbed_audio=artifact.model_copy(update={"uri": "s3://bucket/tts/dubbed.wav"}),
    )

    assert translated.segments[0].segment_id == synthesis.segments[0].segment_id
