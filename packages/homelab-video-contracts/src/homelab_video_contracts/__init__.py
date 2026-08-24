"""Versioned contracts for the video localization pipeline."""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version

from homelab_video_contracts.artifacts import Artifact
from homelab_video_contracts.bilibili import BilibiliAppendRequest
from homelab_video_contracts.bilibili import BilibiliArchivePart
from homelab_video_contracts.bilibili import BilibiliArchiveSnapshot
from homelab_video_contracts.bilibili import BilibiliPartInput
from homelab_video_contracts.bilibili import BilibiliPartResult
from homelab_video_contracts.bilibili import BilibiliPublicationRecord
from homelab_video_contracts.bilibili import BilibiliPublicationStatus
from homelab_video_contracts.bilibili import BilibiliPublishResult
from homelab_video_contracts.bilibili import BilibiliPublishSettings
from homelab_video_contracts.bilibili import BilibiliUploadRequest
from homelab_video_contracts.jobs import JobError
from homelab_video_contracts.jobs import JobStatus
from homelab_video_contracts.jobs import JobType
from homelab_video_contracts.jobs import LocalizationJob
from homelab_video_contracts.jobs import LocalizationJobRequest
from homelab_video_contracts.manifest import StageRecord
from homelab_video_contracts.manifest import VideoManifest
from homelab_video_contracts.rendering import AudioStrategy
from homelab_video_contracts.rendering import MediaQualityReport
from homelab_video_contracts.rendering import RenderRequest
from homelab_video_contracts.rendering import RenderResult
from homelab_video_contracts.rendering import RenderSettings
from homelab_video_contracts.synthesis import SourceSeparationResult
from homelab_video_contracts.synthesis import SynthesisResult
from homelab_video_contracts.transcript import Transcript
from homelab_video_contracts.transcript import TranscriptSegment
from homelab_video_contracts.transcript import TranscriptWord
from homelab_video_contracts.translation import TranslatedSegment
from homelab_video_contracts.translation import TranslatedTimeline
from homelab_video_contracts.youtube import YouTubeChannel
from homelab_video_contracts.youtube import YouTubeVideo


try:
    __version__ = version("homelab-video-contracts")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "Artifact",
    "AudioStrategy",
    "BilibiliAppendRequest",
    "BilibiliArchivePart",
    "BilibiliArchiveSnapshot",
    "BilibiliPartInput",
    "BilibiliPartResult",
    "BilibiliPublicationRecord",
    "BilibiliPublicationStatus",
    "BilibiliPublishResult",
    "BilibiliPublishSettings",
    "BilibiliUploadRequest",
    "JobError",
    "JobStatus",
    "JobType",
    "LocalizationJob",
    "LocalizationJobRequest",
    "MediaQualityReport",
    "RenderRequest",
    "RenderResult",
    "RenderSettings",
    "SourceSeparationResult",
    "StageRecord",
    "SynthesisResult",
    "Transcript",
    "TranscriptSegment",
    "TranscriptWord",
    "TranslatedSegment",
    "TranslatedTimeline",
    "VideoManifest",
    "YouTubeChannel",
    "YouTubeVideo",
    "__version__",
]
