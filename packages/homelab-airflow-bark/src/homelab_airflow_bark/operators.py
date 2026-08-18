"""Airflow operator for Bark notifications."""

from typing import Any
from typing import ClassVar

from airflow.models import BaseOperator
from airflow.utils.context import Context

from homelab_airflow_bark.bark_client import BarkClient
from homelab_airflow_bark.schemas import BarkPushMessage


class BarkNotifyOperator(BaseOperator):
    """Send a Bark notification from an Airflow task.

    Args:
        message: Bark payload as a dict or validated Pydantic model.
        timeout: Request timeout in seconds.
    """

    template_fields = ("message",)
    template_fields_renderers: ClassVar[dict[str, str]] = {"message": "json"}

    def __init__(
        self,
        *,
        message: BarkPushMessage | dict[str, Any],
        timeout: int = 10,
        **kwargs,
    ) -> None:
        """Initialize the operator.

        Args:
            message: Bark payload as a dict or validated Pydantic model.
            timeout: Request timeout in seconds.
            **kwargs: Standard Airflow operator keyword arguments.
        """
        super().__init__(**kwargs)
        self.message = message
        self.timeout = timeout

    def execute(self, _context: Context) -> dict[str, object]:
        """Send the Bark notification.

        Args:
            _context: Airflow task context.

        Returns:
            A dictionary containing the normalized Bark response.
        """
        message = BarkPushMessage.model_validate(self.message)
        client = BarkClient(timeout=self.timeout)
        self.log.info("Sending Bark notification: %s", message.title)
        result = client.send(message)
        self.log.info("Bark notification sent: %s", result.url)
        return {"url": result.url, "status_code": result.status_code, "ok": result.ok, "payload": result.payload}
