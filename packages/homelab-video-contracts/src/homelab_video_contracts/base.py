"""Shared model configuration and validators."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from typing import Any
from typing import Literal
from urllib.parse import urlparse

from pydantic import AfterValidator
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


SCHEMA_VERSION = "1.0"


class ContractModel(BaseModel):
    """Strict immutable base for nested contract values."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class VersionedContract(ContractModel):
    """Base for independently persisted JSON documents."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION


def validate_s3_uri(value: str) -> str:
    """Require an absolute S3 URI with both bucket and object key."""
    parsed = urlparse(value)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError("must be an absolute s3:// URI containing a bucket and object key")
    if parsed.query or parsed.fragment:
        raise ValueError("S3 URI must not contain a query string or fragment")
    return value


def validate_aware_datetime(value: datetime) -> datetime:
    """Require timezone-aware timestamps in persisted contracts."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return value


S3Uri = Annotated[str, AfterValidator(validate_s3_uri)]
AwareDatetime = Annotated[datetime, AfterValidator(validate_aware_datetime)]
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
JsonObject = dict[str, Any]
