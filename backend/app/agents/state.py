"""Typed LangGraph state."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.ai.schemas import Category, EmailAnalysisResult, Priority


class EmailAgentState(BaseModel):
    # input
    email_id: int
    thread_id: str = ""
    sender: str
    recipients: list[str] = Field(default_factory=list)
    subject: str = ""
    body: str = ""
    received_at: datetime | None = None
    preferences: dict[str, str] = Field(default_factory=dict)  # category -> priority rule
    today: date
    want_draft: bool = False

    # working
    injection_flagged: bool = False
    analysis: EmailAnalysisResult | None = None

    # outputs
    category: Category | None = None
    category_confidence: float | None = None
    uncertain: bool = False
    priority: Priority | None = None
    summary: str = ""
    action_required: bool = False
    action_items: list[str] = Field(default_factory=list)
    deadline_text: str | None = None
    deadline_date: date | None = None
    deadline_time: str | None = None
    meeting_details: dict | None = None
    extracted_entities: dict = Field(default_factory=dict)
    reply_required: bool = False
    reply_draft: str | None = None
    approval_status: Literal["not_required", "pending_human_approval"] = "not_required"
    tool_result: dict | None = None
    error: str | None = None
    final_response: dict | None = None
