"""Structured LLM output schemas. All LLM output is validated through these models."""
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    job = "job"
    work = "work"
    meeting = "meeting"
    customer = "customer"
    finance = "finance"
    personal = "personal"
    newsletter = "newsletter"
    promotion = "promotion"
    notification = "notification"
    spam = "spam"
    other = "other"


class Priority(str, Enum):
    urgent = "urgent"
    high = "high"
    medium = "medium"
    low = "low"


PRIORITY_ORDER = {Priority.low: 0, Priority.medium: 1, Priority.high: 2, Priority.urgent: 3}


class EmailAnalysisResult(BaseModel):
    category: Category = Category.other
    category_confidence: float | None = Field(default=None, ge=0, le=1)
    category_reason: str = ""
    priority: Priority = Priority.low
    priority_reason: str = ""
    summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    action_required: bool = False
    action_items: list[str] = Field(default_factory=list)
    deadline_text: str | None = None
    deadline_date: date | None = None  # only when unambiguous
    deadline_time: str | None = None  # "HH:MM" only when explicitly stated
    meeting_details: dict | None = None
    extracted_entities: dict = Field(default_factory=dict)
    reply_required: bool = False

    @field_validator("category", mode="before")
    @classmethod
    def _norm_category(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in Category._value2member_map_:
                return "other"
        return v

    @field_validator("priority", mode="before")
    @classmethod
    def _norm_priority(cls, v):
        if isinstance(v, str):
            v = v.strip().lower()
            if v not in Priority._value2member_map_:
                return "low"
        return v

    @field_validator("deadline_time")
    @classmethod
    def _check_time(cls, v):
        if v is None:
            return v
        parts = v.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit() and 0 <= int(parts[0]) < 24 and 0 <= int(parts[1]) < 60:
            return f"{int(parts[0]):02d}:{int(parts[1]):02d}"
        return None

    @field_validator("key_points", "action_items", mode="before")
    @classmethod
    def _list_of_str(cls, v):
        return [str(x) for x in v] if isinstance(v, list) else []


class EmailPayload(BaseModel):
    """Normalised email passed to the LLM layer."""
    sender: str
    recipients: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    received_at: str = ""
