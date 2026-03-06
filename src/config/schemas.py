from __future__ import annotations

import datetime as dt
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SKIPPED = "skipped"


class SelectorKind(str, Enum):
    BUTTON = "button"
    LINK = "link"
    INPUT = "input"
    TEXTAREA = "textarea"
    SELECT = "select"
    FORM = "form"
    SEARCH = "search"


class JsonSchemaModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Duration(JsonSchemaModel):
    started_at_utc: dt.datetime
    ended_at_utc: dt.datetime
    duration_ms: int = Field(ge=0)


class UrlTarget(JsonSchemaModel):
    url: HttpUrl
