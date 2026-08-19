"""Notify Bark when configured YouTube channels publish videos."""

from datetime import timedelta
from typing import Any

import pendulum
from airflow.datasets import DatasetAlias
from airflow.decorators import dag
from airflow.decorators import task
from airflow.models import Variable
from homelab_airflow_bark.operators import BarkNotifyOperator
from homelab_airflow_providers_youtube.hooks import YouTubeHook
from homelab_airflow_providers_youtube.operators import YouTubeChannelVideosOperator


CHANNELS_VARIABLE = "youtube_watched_channels"
DEFAULT_CHANNELS = ["@EarnMoar"]


def normalize_channel_references(channels: object) -> list[str]:
    """Validate, trim, and deduplicate configured channel IDs or handles."""
    if not isinstance(channels, list) or not channels:
        raise ValueError(f"Airflow Variable {CHANNELS_VARIABLE!r} must be a non-empty JSON list")
    if any(not isinstance(channel, str) or not channel.strip() for channel in channels):
        raise ValueError(f"Airflow Variable {CHANNELS_VARIABLE!r} must contain non-empty strings")

    return list(dict.fromkeys(channel.strip() for channel in channels))


@task
def resolve_watched_channel_ids() -> list[str]:
    """Load channel IDs or handles and resolve handles to permanent IDs."""
    channels = Variable.get(
        CHANNELS_VARIABLE,
        default_var=DEFAULT_CHANNELS,
        deserialize_json=True,
    )
    channel_references = normalize_channel_references(channels)

    hook = YouTubeHook(youtube_conn_id="youtube_default")
    channel_ids = [
        hook.get_channel_by_handle(channel).channel_id if channel.startswith("@") else channel
        for channel in channel_references
    ]
    return list(dict.fromkeys(channel_ids))


@task
def build_bark_notifications(video_batches: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Flatten mapped discovery results into Bark operator arguments."""
    return [
        {
            "message": {
                "title": f"{video.get('channel_title') or 'YouTube'} 发布了新视频",
                "body": video["title"],
                "url": video["source_url"],
                "group": "youtube-updates",
                "isArchive": True,
            }
        }
        for videos in video_batches
        for video in videos
    ]


@dag(
    dag_id="youtube_channel_updates",
    description="Check configured YouTube channels daily and notify Bark about new videos.",
    schedule="@daily",
    start_date=pendulum.datetime(2026, 8, 19, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "shawndeng",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["youtube", "bark"],
)
def youtube_channel_updates_dag():
    """Discover videos for every configured channel and send Bark messages."""
    channel_ids = resolve_watched_channel_ids()

    video_batches = YouTubeChannelVideosOperator.partial(
        task_id="discover_channel_videos",
        published_after="{{ data_interval_start }}",
        published_before="{{ data_interval_end }}",
        max_results=50,
        youtube_conn_id="youtube_default",
        outlet=DatasetAlias("youtube-watched-channel-uploads"),
    ).expand(channel_id=channel_ids)

    notifications = build_bark_notifications(video_batches.output)

    BarkNotifyOperator.partial(
        task_id="notify_bark",
        bark_conn_id="bark_default",
    ).expand_kwargs(notifications)


youtube_channel_updates_dag()
