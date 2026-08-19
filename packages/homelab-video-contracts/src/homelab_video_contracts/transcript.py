"""Speech-to-text timeline contracts."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic import model_validator

from homelab_video_contracts.artifacts import Artifact
from homelab_video_contracts.base import ContractModel
from homelab_video_contracts.base import NonNegativeInt
from homelab_video_contracts.base import PositiveInt
from homelab_video_contracts.base import VersionedContract


class TranscriptWord(ContractModel):
    """One recognized word on the absolute media timeline."""

    start_ms: NonNegativeInt
    end_ms: PositiveInt
    text: Annotated[str, Field(min_length=1)]
    probability: Annotated[float, Field(ge=0, le=1)] | None = None

    @model_validator(mode="after")
    def validate_range(self) -> TranscriptWord:
        """Require a positive word interval."""
        if self.end_ms <= self.start_ms:
            raise ValueError("word end_ms must be greater than start_ms")
        return self


class TranscriptSegment(ContractModel):
    """A stable ASR segment containing zero or more word timestamps."""

    segment_id: Annotated[str, Field(min_length=1)]
    start_ms: NonNegativeInt
    end_ms: PositiveInt
    text: Annotated[str, Field(min_length=1)]
    words: tuple[TranscriptWord, ...] = ()
    speaker: str | None = None

    @model_validator(mode="after")
    def validate_timeline(self) -> TranscriptSegment:
        """Validate the segment range and contained word ordering."""
        if self.end_ms <= self.start_ms:
            raise ValueError("segment end_ms must be greater than start_ms")
        previous_start = self.start_ms
        for word in self.words:
            if word.start_ms < self.start_ms or word.end_ms > self.end_ms:
                raise ValueError("word timestamps must stay inside their segment")
            if word.start_ms < previous_start:
                raise ValueError("words must be ordered by start_ms")
            previous_start = word.start_ms
        return self


class Transcript(VersionedContract):
    """A complete normalized ASR result persisted in RustFS."""

    source_audio: Artifact
    language: Annotated[str, Field(min_length=2)]
    duration_ms: PositiveInt
    provider: Annotated[str, Field(min_length=1)]
    model: Annotated[str, Field(min_length=1)]
    segments: tuple[TranscriptSegment, ...]
    raw_response_artifacts: tuple[Artifact, ...] = ()

    @model_validator(mode="after")
    def validate_segments(self) -> Transcript:
        """Require unique, ordered segments within the media duration."""
        segment_ids: set[str] = set()
        previous_start = 0
        for segment in self.segments:
            if segment.segment_id in segment_ids:
                raise ValueError("segment_id must be unique within a transcript")
            if segment.start_ms < previous_start:
                raise ValueError("segments must be ordered by start_ms")
            if segment.end_ms > self.duration_ms:
                raise ValueError("segment timestamp exceeds transcript duration")
            segment_ids.add(segment.segment_id)
            previous_start = segment.start_ms
        return self
