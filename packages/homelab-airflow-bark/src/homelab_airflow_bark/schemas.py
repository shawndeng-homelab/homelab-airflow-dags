"""Validated Bark payload schemas."""

from typing import Literal

from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class BarkPushMessage(BaseModel):
    """A Bark notification payload without connection credentials."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, populate_by_name=True)

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
        """Convert the model into a Bark-compatible JSON payload."""
        payload = self.model_dump(
            mode="json",
            by_alias=True,
            exclude={"call", "auto_copy", "is_archive"},
            exclude_none=True,
        )
        payload["call"] = 1 if self.call else None
        payload["autoCopy"] = 1 if self.auto_copy else None
        payload["isArchive"] = 1 if self.is_archive else None
        return {key: value for key, value in payload.items() if value is not None}
