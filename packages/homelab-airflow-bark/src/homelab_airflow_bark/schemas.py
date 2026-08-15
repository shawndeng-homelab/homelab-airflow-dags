"""Validated Bark payload schemas."""

from typing import Literal

from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class BarkPushMessage(BaseModel):
    """Validated Bark push payload.

    Attributes:
        base_url: Bark server base URL.
        device_key: Device key used to identify the target device.
        title: Notification title.
        body: Notification body.
        subtitle: Optional notification subtitle.
        markdown: Optional markdown body.
        level: Interruption level accepted by Bark.
        url: Optional click-through URL.
        group: Optional notification grouping key.
        icon: Optional icon URL.
        sound: Optional notification sound.
        badge: Optional badge count.
        call: Whether Bark should ring for a call-style alert.
        copy_text: Optional clipboard value.
        auto_copy: Whether Bark should auto-copy the payload to clipboard.
        is_archive: Whether the notification should be archived.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

    base_url: AnyHttpUrl
    device_key: str = Field(min_length=1)
    title: str = Field(min_length=1)
    body: str = Field(min_length=1)
    subtitle: str | None = None
    markdown: str | None = None
    level: Literal["critical", "active", "timeSensitive", "passive"] = "active"
    url: AnyHttpUrl | None = None
    group: str | None = None
    icon: AnyHttpUrl | None = None
    sound: str | None = None
    badge: int | None = Field(default=None, ge=0)
    call: bool = False
    copy_text: str | None = Field(default=None, alias="copy")
    auto_copy: bool = Field(default=False, alias="autoCopy")
    is_archive: bool = Field(default=False, alias="isArchive")

    def to_payload(self) -> dict[str, object]:
        """Convert the model into the Bark API payload.

        Returns:
            A Bark-compatible JSON payload using Bark field names.
        """
        payload = self.model_dump(
            mode="json",
            by_alias=True,
            exclude={"base_url", "call", "auto_copy", "is_archive"},
            exclude_none=True,
        )
        payload["call"] = 1 if self.call else None
        payload["autoCopy"] = 1 if self.auto_copy else None
        payload["isArchive"] = 1 if self.is_archive else None
        return {key: value for key, value in payload.items() if value is not None}
