"""Target schema: a triage card for a Guesty API partner support ticket."""

from __future__ import annotations

import copy
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Surface(str, Enum):
    open_api = "open_api"
    partners_api = "partners_api"
    booking_engine_api = "booking_engine_api"
    webhooks = "webhooks"
    unknown = "unknown"


class Category(str, Enum):
    authentication = "authentication"
    rate_limit = "rate_limit"
    integration_setup = "integration_setup"
    data_sync = "data_sync"
    bug = "bug"
    how_to_question = "how_to_question"
    feature_request = "feature_request"
    other = "other"


class Priority(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Language(str, Enum):
    en = "en"
    uk = "uk"
    ru = "ru"
    es = "es"
    mixed = "mixed"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"


class EntityIds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_ids: list[str]
    listing_ids: list[str]
    reservation_ids: list[str]

    @field_validator("account_ids", "listing_ids", "reservation_ids")
    @classmethod
    def no_placeholder_ids(cls, v: list[str]) -> list[str]:
        bad = [i for i in v if i.strip().lower() in PLACEHOLDERS]
        if bad:
            raise ValueError(f"use an empty list instead of placeholder IDs {bad}")
        return v


class ApiError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str | None
    http_method: HttpMethod | None
    # Only failing calls belong here; a 200 is not an API error.
    http_status: int | None = Field(ge=400, le=599)
    error_message: str | None


class TicketTriage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    partner_name: str | None
    surface: Surface
    category: Category
    priority: Priority
    language: Language
    entity_ids: EntityIds
    api_errors: list[ApiError]
    needs_engineering: bool
    summary: str = Field(min_length=1, max_length=200)

    @field_validator("partner_name")
    @classmethod
    def no_placeholder_strings(cls, v: str | None) -> str | None:
        if v is not None and v.strip().lower() in PLACEHOLDERS:
            raise ValueError(f"use JSON null instead of the string {v!r}")
        return v


PLACEHOLDERS = {"", "null", "none", "n/a", "na", "unknown", "not provided", "not specified"}


# Keywords that some providers reject in strict mode; Pydantic still enforces them locally,
# so a violation goes through the repair step instead of being silently accepted.
_LOCAL_ONLY_KEYWORDS = {"minimum", "maximum", "minLength", "maxLength", "title", "default"}


def _inline(node, defs):
    if isinstance(node, dict):
        if "$ref" in node:
            return _inline(copy.deepcopy(defs[node["$ref"].split("/")[-1]]), defs)
        out = {k: _inline(v, defs) for k, v in node.items() if k not in _LOCAL_ONLY_KEYWORDS}
        if out.get("type") == "object":
            out["additionalProperties"] = False
            out["required"] = list(out.get("properties", {}))
        return out
    if isinstance(node, list):
        return [_inline(v, defs) for v in node]
    return node


def provider_json_schema() -> dict:
    """Self-contained strict JSON Schema (no $ref) accepted by OpenAI, Gemini and Ollama."""
    raw = TicketTriage.model_json_schema()
    defs = raw.pop("$defs", {})
    return _inline(raw, defs)
