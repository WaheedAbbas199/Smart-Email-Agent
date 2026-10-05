"""Data access helpers."""
from __future__ import annotations

from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.db.models import AgentAction, Email, EmailAnalysis, OAuthToken, ReplyDraft, UserPreference


class EmailRepository:
    def __init__(self, db: Session, user_id: int):
        self.db, self.user_id = db, user_id

    def get(self, email_id: int) -> Email | None:
        return (self.db.query(Email).options(joinedload(Email.analysis))
                .filter(Email.id == email_id, Email.user_id == self.user_id).first())

    def get_by_external(self, external_id: str) -> Email | None:
        return self.db.query(Email).filter(Email.user_id == self.user_id, Email.external_id == external_id).first()

    def list(self, filter_: str = "all", q: str | None = None, category: str | None = None,
             priority: str | None = None, limit: int = 200) -> list[Email]:
        query = (self.db.query(Email).options(joinedload(Email.analysis))
                 .outerjoin(EmailAnalysis).filter(Email.user_id == self.user_id))
        if filter_ == "urgent":
            query = query.filter(EmailAnalysis.priority == "urgent")
        elif filter_ == "high":
            query = query.filter(EmailAnalysis.priority == "high")
        elif filter_ == "important":
            query = query.filter(EmailAnalysis.priority.in_(["urgent", "high"]))
        elif filter_ == "action":
            query = query.filter(EmailAnalysis.action_required.is_(True))
        elif filter_ in ("job", "work", "personal", "meeting", "customer", "finance", "newsletter", "promotion", "spam"):
            query = query.filter(EmailAnalysis.category == filter_)
        if category:
            query = query.filter(EmailAnalysis.category == category)
        if priority:
            query = query.filter(EmailAnalysis.priority == priority)
        if q:
            like = f"%{q}%"
            query = query.filter(or_(Email.subject.ilike(like), Email.sender.ilike(like), Email.body.ilike(like)))
        return query.order_by(Email.received_at.desc()).limit(limit).all()

    def unanalyzed(self) -> list[Email]:
        return (self.db.query(Email).outerjoin(EmailAnalysis)
                .filter(Email.user_id == self.user_id, EmailAnalysis.id.is_(None)).all())

    def upcoming_deadlines(self, today: date, limit: int = 10) -> list[Email]:
        return (self.db.query(Email).join(EmailAnalysis)
                .options(joinedload(Email.analysis))
                .filter(Email.user_id == self.user_id, EmailAnalysis.deadline_date >= today,
                        EmailAnalysis.action_required.is_(True))
                .order_by(EmailAnalysis.deadline_date).limit(limit).all())


class DraftRepository:
    def __init__(self, db: Session, user_id: int):
        self.db, self.user_id = db, user_id

    def get(self, draft_id: int) -> ReplyDraft | None:
        return (self.db.query(ReplyDraft).options(joinedload(ReplyDraft.email))
                .filter(ReplyDraft.id == draft_id, ReplyDraft.user_id == self.user_id).first())

    def list(self, status: str | None = None) -> list[ReplyDraft]:
        q = self.db.query(ReplyDraft).options(joinedload(ReplyDraft.email)).filter(ReplyDraft.user_id == self.user_id)
        if status:
            q = q.filter(ReplyDraft.status == status)
        return q.order_by(ReplyDraft.created_at.desc()).all()

    def active_for_email(self, email_id: int) -> ReplyDraft | None:
        return (self.db.query(ReplyDraft)
                .filter(ReplyDraft.email_id == email_id, ReplyDraft.user_id == self.user_id,
                        ReplyDraft.status.in_(["draft", "approved", "failed"]))
                .order_by(ReplyDraft.created_at.desc()).first())

    def count(self, *statuses: str) -> int:
        return self.db.query(ReplyDraft).filter(ReplyDraft.user_id == self.user_id,
                                                ReplyDraft.status.in_(statuses)).count()


class ActionRepository:
    def __init__(self, db: Session, user_id: int):
        self.db, self.user_id = db, user_id

    def record(self, action: str, email_id: int | None = None, detail: dict | None = None,
               success: bool = True, latency_ms: int | None = None) -> AgentAction:
        row = AgentAction(user_id=self.user_id, email_id=email_id, action=action, detail=detail or {},
                          success=success, latency_ms=latency_ms)
        self.db.add(row)
        self.db.commit()
        return row

    def recent(self, limit: int = 50) -> list[AgentAction]:
        return (self.db.query(AgentAction).filter(AgentAction.user_id == self.user_id)
                .order_by(AgentAction.id.desc()).limit(limit).all())


class PreferenceRepository:
    def __init__(self, db: Session, user_id: int):
        self.db, self.user_id = db, user_id

    def by_kind(self, kind: str) -> dict[str, str]:
        rows = self.db.query(UserPreference).filter(UserPreference.user_id == self.user_id,
                                                    UserPreference.kind == kind).all()
        return {r.key: r.value for r in rows}

    def upsert(self, kind: str, key: str, value: str) -> None:
        row = self.db.query(UserPreference).filter_by(user_id=self.user_id, kind=kind, key=key).first()
        if row:
            row.value = value
        else:
            self.db.add(UserPreference(user_id=self.user_id, kind=kind, key=key, value=value))

    def delete(self, kind: str, key: str) -> None:
        self.db.query(UserPreference).filter_by(user_id=self.user_id, kind=kind, key=key).delete()


class TokenRepository:
    def __init__(self, db: Session, user_id: int):
        self.db, self.user_id = db, user_id

    def get(self) -> OAuthToken | None:
        return self.db.query(OAuthToken).filter_by(user_id=self.user_id).first()
