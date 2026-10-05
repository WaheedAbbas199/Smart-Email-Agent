"""Database models."""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base, utcnow


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    emails: Mapped[list["Email"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    preferences: Mapped[list["UserPreference"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    drafts: Mapped[list["ReplyDraft"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    actions: Mapped[list["AgentAction"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    oauth_token: Mapped["OAuthToken | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    provider: Mapped[str] = mapped_column(String(50), default="google")
    access_token_enc: Mapped[str] = mapped_column(Text)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    scope: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    user: Mapped[User] = relationship(back_populates="oauth_token")


class Email(Base):
    __tablename__ = "emails"
    __table_args__ = (UniqueConstraint("user_id", "external_id", name="uq_email_user_external"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    thread_id: Mapped[str] = mapped_column(String(255), default="")
    sender: Mapped[str] = mapped_column(String(500))
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(String(1000), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    source: Mapped[str] = mapped_column(String(20), default="demo")

    user: Mapped[User] = relationship(back_populates="emails")
    analysis: Mapped["EmailAnalysis | None"] = relationship(back_populates="email", uselist=False, cascade="all, delete-orphan")
    drafts: Mapped[list["ReplyDraft"]] = relationship(back_populates="email", cascade="all, delete-orphan")


class EmailAnalysis(Base):
    __tablename__ = "email_analyses"
    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), unique=True)
    category: Mapped[str] = mapped_column(String(30))
    category_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertain: Mapped[bool] = mapped_column(Boolean, default=False)
    category_reason: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(20))
    priority_reason: Mapped[str] = mapped_column(Text, default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    key_points: Mapped[list] = mapped_column(JSON, default=list)
    action_required: Mapped[bool] = mapped_column(Boolean, default=False)
    action_items: Mapped[list] = mapped_column(JSON, default=list)
    deadline_text: Mapped[str | None] = mapped_column(String(200), nullable=True)
    deadline_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    deadline_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    meeting_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    extracted_entities: Mapped[dict] = mapped_column(JSON, default=dict)
    reply_required: Mapped[bool] = mapped_column(Boolean, default=False)
    injection_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    model: Mapped[str] = mapped_column(String(100), default="")
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    email: Mapped[Email] = relationship(back_populates="analysis")


class ReplyDraft(Base):
    """status: draft -> approved -> sending -> sent | failed ; or rejected."""
    __tablename__ = "reply_drafts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), index=True)
    original_body: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    approved_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    modified: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    send_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user: Mapped[User] = relationship(back_populates="drafts")
    email: Mapped[Email] = relationship(back_populates="drafts")


class AgentAction(Base):
    __tablename__ = "agent_actions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    email_id: Mapped[int | None] = mapped_column(ForeignKey("emails.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user: Mapped[User] = relationship(back_populates="actions")


class UserPreference(Base):
    """kind='priority_rule': key=category, value=priority. kind='setting': key=name, value=string."""
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("user_id", "kind", "key", name="uq_pref"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[str] = mapped_column(String(200))
    user: Mapped[User] = relationship(back_populates="preferences")
