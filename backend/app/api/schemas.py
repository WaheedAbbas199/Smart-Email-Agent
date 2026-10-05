"""API response/request models."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.ai.schemas import Category, Priority


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    category: str
    category_confidence: float | None
    uncertain: bool
    category_reason: str
    priority: str
    priority_reason: str
    summary: str
    key_points: list[str]
    action_required: bool
    action_items: list[str]
    deadline_text: str | None
    deadline_date: date | None
    deadline_time: str | None
    meeting_details: dict | None
    extracted_entities: dict
    reply_required: bool
    injection_flagged: bool
    model: str


class EmailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sender: str
    recipients: list[str]
    subject: str
    received_at: datetime
    source: str
    thread_id: str
    body: str | None = None
    analysis: AnalysisOut | None = None


class DraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email_id: int
    body: str
    original_body: str
    status: str
    modified: bool
    approved_by: str | None
    approved_at: datetime | None
    sent_at: datetime | None
    send_result: dict | None
    created_at: datetime
    email: EmailOut | None = None


class DraftRequest(BaseModel):
    instructions: str | None = Field(default=None, max_length=500)
    regenerate: bool = False


class DraftUpdate(BaseModel):
    body: str = Field(min_length=1, max_length=20000)


class SendRequest(BaseModel):
    confirm: bool = False


class SettingsUpdate(BaseModel):
    priority_rules: dict[str, str | None] | None = None
    settings: dict[str, bool] | None = None


class ErrorBody(BaseModel):
    code: str
    message: str


CATEGORIES = [c.value for c in Category]
PRIORITIES = [p.value for p in Priority]
