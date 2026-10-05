"""Reply drafting + human approval + sending.

Invariants:
- The LLM/agent can only create drafts. Sending requires: status == approved AND explicit confirm.
- The approved text is snapshotted (approved_body); editing after approval resets to draft.
- Status moves to 'sending' (committed) BEFORE calling the provider; there is NO automatic retry,
  so a double click or retry can never send twice.
"""
import logging
import re
import time

from sqlalchemy.orm import Session

from app.agents.email_agent import EmailAgent
from app.ai.llm_base import LLMError
from app.db.database import utcnow
from app.db.models import Email, ReplyDraft
from app.db.repositories import ActionRepository, DraftRepository, EmailRepository
from app.integrations.provider import EmailProvider, EmailProviderError

logger = logging.getLogger(__name__)


class ReplyError(Exception):
    """Business-rule violation (maps to HTTP 409/422)."""


class ReplyService:
    def __init__(self, db: Session, user_id: int, user_email: str, provider: EmailProvider, agent: EmailAgent):
        self.db, self.user_id, self.user_email = db, user_id, user_email
        self.provider, self.agent = provider, agent
        self.drafts = DraftRepository(db, user_id)
        self.emails = EmailRepository(db, user_id)
        self.actions = ActionRepository(db, user_id)

    def _draft(self, draft_id: int) -> ReplyDraft:
        d = self.drafts.get(draft_id)
        if not d:
            raise LookupError("Draft not found")
        return d

    def create_or_regenerate(self, email_id: int, instructions: str | None = None, regenerate: bool = False) -> ReplyDraft:
        email = self.emails.get(email_id)
        if not email:
            raise LookupError("Email not found")
        if not email.analysis:
            raise ReplyError("Analyze the email before drafting a reply")
        if email.analysis.injection_flagged:
            raise ReplyError("This email contains instructions aimed at an AI assistant; no reply will be drafted")
        existing = self.drafts.active_for_email(email_id)
        if existing and existing.status in ("approved",):
            raise ReplyError("An approved draft already exists; reject it first to create a new one")
        if existing and not regenerate:
            return existing
        start = time.perf_counter()
        try:
            body = self.agent.llm.draft_reply(
                {"sender": email.sender, "recipients": email.recipients, "subject": email.subject,
                 "body": email.body, "received_at": email.received_at.isoformat()},
                self._analysis_dict(email), instructions)
        except LLMError as exc:
            self.actions.record("draft_reply", email_id, {"error": str(exc)}, success=False)
            raise
        if existing:
            existing.body = existing.original_body = body
            existing.status, existing.modified, existing.approved_body = "draft", False, None
            draft = existing
        else:
            draft = ReplyDraft(user_id=self.user_id, email_id=email_id, original_body=body, body=body)
            self.db.add(draft)
        self.db.commit()
        self.actions.record("draft_reply", email_id, {"draft_id": draft.id, "regenerated": bool(existing)},
                            latency_ms=int((time.perf_counter() - start) * 1000))
        return draft

    @staticmethod
    def _analysis_dict(email: Email) -> dict:
        a = email.analysis
        return {"category": a.category, "priority": a.priority, "summary": a.summary,
                "action_items": a.action_items, "deadline_text": a.deadline_text}

    def edit(self, draft_id: int, body: str) -> ReplyDraft:
        d = self._draft(draft_id)
        if d.status in ("sending", "sent", "rejected"):
            raise ReplyError(f"Draft is {d.status} and can no longer be edited")
        body = body.strip()
        if not body:
            raise ReplyError("Draft body cannot be empty")
        d.body, d.modified = body, body != d.original_body
        d.status, d.approved_body, d.approved_by, d.approved_at = "draft", None, None, None  # edits need re-approval
        self.db.commit()
        self.actions.record("edit_draft", d.email_id, {"draft_id": d.id, "modified": d.modified})
        return d

    def approve(self, draft_id: int) -> ReplyDraft:
        d = self._draft(draft_id)
        if d.status != "draft":
            raise ReplyError(f"Only drafts can be approved (current status: {d.status})")
        d.status, d.approved_body = "approved", d.body
        d.approved_by, d.approved_at = self.user_email, utcnow()
        self.db.commit()
        self.actions.record("approve_draft", d.email_id, {"draft_id": d.id, "approved_by": self.user_email,
                                                           "modified": d.modified})
        return d

    def reject(self, draft_id: int) -> ReplyDraft:
        d = self._draft(draft_id)
        if d.status in ("sending", "sent"):
            raise ReplyError(f"Draft is {d.status} and cannot be rejected")
        d.status = "rejected"
        self.db.commit()
        self.actions.record("reject_draft", d.email_id, {"draft_id": d.id})
        return d

    def send(self, draft_id: int, confirm: bool) -> ReplyDraft:
        if not confirm:
            raise ReplyError("Sending requires explicit confirmation (confirm=true)")
        d = self._draft(draft_id)
        if d.status != "approved" or not d.approved_body:
            raise ReplyError(f"Draft must be approved before sending (current status: {d.status})")
        email = d.email
        subject = email.subject if re.match(r"(?i)^re:", email.subject) else f"Re: {email.subject}"
        to = re.search(r"<([^>]+)>", email.sender)
        to_addr = to.group(1) if to else email.sender
        d.status = "sending"  # lock first: concurrent/duplicate requests are now rejected
        self.db.commit()
        start = time.perf_counter()
        try:
            result = self.provider.send_email(to_addr, subject, d.approved_body, email.thread_id or None)
        except EmailProviderError as exc:
            d.status, d.send_result = "failed", {"ok": False, "error": str(exc)}
            self.db.commit()
            self.actions.record("send_email", d.email_id, {"draft_id": d.id, "error": str(exc)}, success=False,
                                latency_ms=int((time.perf_counter() - start) * 1000))
            raise
        d.status, d.sent_at = "sent", utcnow()
        d.send_result = {"ok": result.ok, "message_id": result.message_id, **result.detail}
        self.db.commit()
        self.actions.record("send_email", d.email_id,
                            {"draft_id": d.id, "approved_by": d.approved_by, "modified": d.modified,
                             "message_id": result.message_id}, latency_ms=int((time.perf_counter() - start) * 1000))
        return d
