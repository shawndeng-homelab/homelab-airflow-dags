"""Standard Airflow notifier for Bark."""

from __future__ import annotations

from typing import Literal

from airflow.notifications.basenotifier import BaseNotifier
from airflow.utils.context import Context

from homelab_airflow_bark.hooks import BarkHook
from homelab_airflow_bark.schemas import BarkPushMessage


class BarkNotifier(BaseNotifier):
    """Send templated Airflow lifecycle notifications through Bark."""

    template_fields = (
        "title",
        "body",
        "subtitle",
        "markdown",
        "url",
        "group",
        "icon",
        "sound",
        "copy_text",
    )

    def __init__(
        self,
        *,
        title: str,
        body: str,
        bark_conn_id: str = BarkHook.default_conn_name,
        timeout: float | None = None,
        subtitle: str | None = None,
        markdown: str | None = None,
        level: Literal["critical", "active", "timeSensitive", "passive"] = "active",
        url: str | None = None,
        group: str | None = None,
        icon: str | None = None,
        sound: str | None = None,
        badge: int | None = None,
        call: bool = False,
        copy_text: str | None = None,
        auto_copy: bool = False,
        is_archive: bool = False,
    ) -> None:
        """Initialize a reusable, templated Bark callback."""
        self.title = title
        self.body = body
        self.bark_conn_id = bark_conn_id
        self.timeout = timeout
        self.subtitle = subtitle
        self.markdown = markdown
        self.level = level
        self.url = url
        self.group = group
        self.icon = icon
        self.sound = sound
        self.badge = badge
        self.call = call
        self.copy_text = copy_text
        self.auto_copy = auto_copy
        self.is_archive = is_archive
        super().__init__()

    def notify(self, _context: Context) -> None:
        """Send the rendered callback message."""
        message = BarkPushMessage(
            title=self.title,
            body=self.body,
            subtitle=self.subtitle,
            markdown=self.markdown,
            level=self.level,
            url=self.url,
            group=self.group,
            icon=self.icon,
            sound=self.sound,
            badge=self.badge,
            call=self.call,
            copy=self.copy_text,
            autoCopy=self.auto_copy,
            isArchive=self.is_archive,
        )
        self.log.info("Sending Bark notification: %s", message.title)
        BarkHook(self.bark_conn_id, timeout=self.timeout).send(message)
        self.log.info("Bark notification sent")
