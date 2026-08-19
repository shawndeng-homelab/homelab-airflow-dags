"""Speech synthesis and source-separation result contracts."""

from __future__ import annotations

from typing import Annotated

from pydantic import Field
from pydantic import model_validator

from homelab_video_contracts.artifacts import Artifact
from homelab_video_contracts.base import ContractModel
from homelab_video_contracts.base import NonNegativeInt
from homelab_video_contracts.base import PositiveInt
from homelab_video_contracts.base import VersionedContract


class SynthesizedSegment(ContractModel):
    """One synthesized utterance mapped to a translated segment."""

    segment_id: Annotated[str, Field(min_length=1)]
    target_start_ms: NonNegativeInt
    target_end_ms: PositiveInt
    text: Annotated[str, Field(min_length=1)]
    voice: Annotated[str, Field(min_length=1)]
    audio: Artifact
    actual_duration_ms: PositiveInt

    @model_validator(mode="after")
    def validate_range(self) -> SynthesizedSegment:
        """Require a positive target window."""
        if self.target_end_ms <= self.target_start_ms:
            raise ValueError("target_end_ms must be greater than target_start_ms")
        return self


class SynthesisResult(VersionedContract):
    """A complete external TTS result ready for local FFmpeg mixing."""

    source_timeline: Artifact
    language: Annotated[str, Field(min_length=2)]
    provider: Annotated[str, Field(min_length=1)]
    model: Annotated[str, Field(min_length=1)]
    voice: Annotated[str, Field(min_length=1)]
    segments: tuple[SynthesizedSegment, ...]
    dubbed_audio: Artifact

    @model_validator(mode="after")
    def validate_segment_ids(self) -> SynthesisResult:
        """Require a single synthesized result per stable segment ID."""
        segment_ids = [segment.segment_id for segment in self.segments]
        if len(segment_ids) != len(set(segment_ids)):
            raise ValueError("segment_id must be unique within a synthesis result")
        return self


class SourceSeparationResult(VersionedContract):
    """Optional externally computed voice and accompaniment stems."""

    source_audio: Artifact
    provider: Annotated[str, Field(min_length=1)]
    model: Annotated[str, Field(min_length=1)]
    vocals: Artifact
    accompaniment: Artifact
