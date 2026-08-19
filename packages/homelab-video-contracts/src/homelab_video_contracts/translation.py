"""Translated timeline contracts."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic import model_validator

from homelab_video_contracts.artifacts import Artifact
from homelab_video_contracts.base import ContractModel
from homelab_video_contracts.base import NonNegativeInt
from homelab_video_contracts.base import PositiveInt
from homelab_video_contracts.base import VersionedContract


class TranslatedSegment(ContractModel):
    """One translated segment retaining the stable ASR segment ID."""

    segment_id: Annotated[str, Field(min_length=1)]
    source_start_ms: NonNegativeInt
    source_end_ms: PositiveInt
    source_text: Annotated[str, Field(min_length=1)]
    translated_text: Annotated[str, Field(min_length=1)]
    speaker: str | None = None
    translation_version: Annotated[int, Field(ge=1)] = 1

    @model_validator(mode="after")
    def validate_range(self) -> TranslatedSegment:
        """Require a positive source interval."""
        if self.source_end_ms <= self.source_start_ms:
            raise ValueError("source_end_ms must be greater than source_start_ms")
        return self


class TranslatedTimeline(VersionedContract):
    """The canonical timeline used by subtitles, TTS, and human review."""

    source_transcript: Artifact
    source_language: Annotated[str, Field(min_length=2)]
    target_language: Annotated[str, Field(min_length=2)]
    provider: Annotated[str, Field(min_length=1)]
    model: Annotated[str, Field(min_length=1)]
    segments: tuple[TranslatedSegment, ...]
    subtitle_srt: Artifact | None = None
    subtitle_ass: Artifact | None = None

    @model_validator(mode="after")
    def validate_segments(self) -> TranslatedTimeline:
        """Require unique stable IDs and chronological source intervals."""
        segment_ids: set[str] = set()
        previous_start = 0
        for segment in self.segments:
            if segment.segment_id in segment_ids:
                raise ValueError("segment_id must be unique within a translated timeline")
            if segment.source_start_ms < previous_start:
                raise ValueError("translated segments must be ordered by source_start_ms")
            segment_ids.add(segment.segment_id)
            previous_start = segment.source_start_ms
        return self
