"""Operators that submit work to the external localization service."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from typing import ClassVar

from airflow.exceptions import AirflowException
from airflow.models import BaseOperator
from airflow.utils.context import Context

from homelab_airflow_providers_localization.hooks.localization import LocalizationHook
from homelab_airflow_providers_localization.models import JobStatus
from homelab_airflow_providers_localization.models import LocalizationJob
from homelab_airflow_providers_localization.models import parse_localization_job
from homelab_airflow_providers_localization.triggers.localization import LocalizationJobTrigger


class LocalizationJobOperator(BaseOperator):
    """Submit a localization job and wait for its result."""

    template_fields = ("job_type", "input_uri", "output_prefix", "parameters", "idempotency_key")
    template_fields_renderers: ClassVar[dict[str, str]] = {"parameters": "json"}

    def __init__(
        self,
        *,
        job_type: str,
        input_uri: str,
        output_prefix: str,
        parameters: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
        localization_conn_id: str = LocalizationHook.default_conn_name,
        poll_interval: float = 10.0,
        job_timeout: float | None = 7200,
        deferrable: bool = True,
        **kwargs: Any,
    ) -> None:
        """Initialize a remote localization job."""
        super().__init__(**kwargs)
        if poll_interval <= 0:
            raise ValueError("poll_interval must be greater than zero")
        if job_timeout is not None and job_timeout <= 0:
            raise ValueError("job_timeout must be greater than zero")
        self.job_type = job_type
        self.input_uri = input_uri
        self.output_prefix = output_prefix
        self.parameters = parameters or {}
        self.idempotency_key = idempotency_key
        self.localization_conn_id = localization_conn_id
        self.poll_interval = poll_interval
        self.job_timeout = job_timeout
        self.deferrable = deferrable

    def execute(self, context: Context) -> dict[str, Any]:
        """Submit work and defer by default while it runs remotely."""
        hook = LocalizationHook(self.localization_conn_id)
        job = hook.submit_job(
            job_type=self.job_type,
            input_uri=self.input_uri,
            output_prefix=self.output_prefix,
            parameters=self.parameters,
            idempotency_key=self.idempotency_key or self._default_idempotency_key(context),
        )
        self.log.info("Submitted localization job %s (%s)", job.job_id, job.job_type)
        if job.is_terminal:
            return self._require_success(job)
        if not self.deferrable:
            return self._require_success(hook.wait_for_job(job.job_id, poll_interval=self.poll_interval))

        timeout = timedelta(seconds=self.job_timeout) if self.job_timeout is not None else None
        self.defer(
            trigger=LocalizationJobTrigger(
                job_id=job.job_id,
                localization_conn_id=self.localization_conn_id,
                poll_interval=self.poll_interval,
            ),
            method_name="execute_complete",
            timeout=timeout,
        )
        raise AssertionError("BaseOperator.defer() unexpectedly returned")

    def execute_complete(self, context: Context, event: dict[str, Any] | None = None) -> dict[str, Any]:
        """Validate the trigger event and return the JSON-safe job result."""
        if not event or event.get("status") != "success":
            message = event.get("message", "Missing trigger event") if event else "Missing trigger event"
            raise AirflowException(f"Localization job polling failed: {message}")
        return self._require_success(parse_localization_job(event.get("job")))

    def _default_idempotency_key(self, context: Context) -> str:
        task_instance = context["ti"]
        return f"{task_instance.dag_id}:{task_instance.run_id}:{task_instance.task_id}:{task_instance.map_index}"

    @staticmethod
    def _require_success(job: LocalizationJob) -> dict[str, Any]:
        if job.status is not JobStatus.SUCCEEDED:
            raise AirflowException(f"Localization job {job.job_id!r} ended with status {job.status!r}")
        return job.as_dict()


class _FixedJobTypeOperator(LocalizationJobOperator):
    """Base class for discoverable operators with a fixed service job type."""

    job_type_name: ClassVar[str]

    def __init__(self, *, input_uri: str, output_prefix: str, **kwargs: Any) -> None:
        super().__init__(job_type=self.job_type_name, input_uri=input_uri, output_prefix=output_prefix, **kwargs)


class VideoDownloadOperator(_FixedJobTypeOperator):
    """Download a source video into object storage."""

    job_type_name = "download"


class AudioTranscriptionOperator(_FixedJobTypeOperator):
    """Transcribe audio through the service external ASR integration."""

    job_type_name = "transcribe"


class SubtitleTranslationOperator(_FixedJobTypeOperator):
    """Translate a timestamped subtitle timeline."""

    job_type_name = "translate_subtitles"


class SourceSeparationOperator(_FixedJobTypeOperator):
    """Separate voice and background stems when voice replacement requires it."""

    job_type_name = "separate_audio"


class SpeechSynthesisOperator(_FixedJobTypeOperator):
    """Synthesize localized speech from a translated timeline."""

    job_type_name = "synthesize_speech"


class VideoRenderOperator(_FixedJobTypeOperator):
    """Mix localized audio and optionally burn subtitles into the video."""

    job_type_name = "render_video"
