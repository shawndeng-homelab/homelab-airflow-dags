"""Airflow operator for explicit Bark notification tasks."""

from typing import Any
from typing import ClassVar

from airflow.models import BaseOperator
from airflow.utils.context import Context

from homelab_airflow_bark.hooks import BarkHook
from homelab_airflow_bark.schemas import BarkPushMessage


class BarkNotifyOperator(BaseOperator):
    """Send a Bark notification as an explicit Airflow task."""

    template_fields = ("message", "bark_conn_id")
    template_fields_renderers: ClassVar[dict[str, str]] = {"message": "json"}

    def __init__(
        self,
        *,
        message: BarkPushMessage | dict[str, Any],
        bark_conn_id: str = BarkHook.default_conn_name,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the operator."""
        super().__init__(**kwargs)
        self.message = message
        self.bark_conn_id = bark_conn_id
        self.timeout = timeout

    def execute(self, _context: Context) -> dict[str, object]:
        """Send the notification and return its normalized response."""
        message = BarkPushMessage.model_validate(self.message)
        self.log.info("Sending Bark notification: %s", message.title)
        result = BarkHook(self.bark_conn_id, timeout=self.timeout).send(message)
        self.log.info("Bark notification sent")
        return {
            "url": result.url,
            "status_code": result.status_code,
            "ok": result.ok,
            "payload": result.payload,
        }
