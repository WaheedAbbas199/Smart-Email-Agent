"""Email ingestion, analysis orchestration and dashboard aggregation."""
import logging
import time
from datetime import date

from sqlalchemy.orm import Session

from app.agents.email_agent import EmailAgent
from app.db.models import Email, EmailAnalysis
from app.db.repositories import ActionRepository, DraftRepository, EmailRepository
from app.integrations.provider import EmailProvider
from app.services.preference_service import PreferenceService

logger = logging.getLogger(__name__)


class AnalysisFailed(Exception):
    pass


class EmailService:
    def __init__(self, db: Session, user_id: int, provider: EmailProvider, agent: EmailAgent):
        self.db, self.user_id, self.provider, self.agent = db, user_id, provider, agent
        self.emails = EmailRepository(db, user_id)
        self.actions = ActionRepository(db, user_id)

    def sync(self, max_results: int = 25) -> int:
        start, new = time.perf_counter(), 0
        for raw in self.provider.fetch_emails(max_results):
            if self.emails.get_by_external(raw.external_id):
                continue
            self.db.add(Email(user_id=self.user_id, external_id=raw.external_id, thread_id=raw.thread_id,
                              sender=raw.sender, recipients=raw.recipients, subject=raw.subject,
                              body=raw.body, received_at=raw.received_at, source=self.provider.source))
            new += 1
        self.db.commit()
        self.actions.record("sync_emails", detail={"new": new, "source": self.provider.source},
                            latency_ms=int((time.perf_counter() - start) * 1000))
        return new

    def analyze(self, email_id: int, force: bool = False) -> Email:
        email = self.emails.get(email_id)
        if not email:
            raise LookupError("Email not found")
        if email.analysis and not force:
            return email
        prefs = PreferenceService(self.db, self.user_id).priority_rules()
        start = time.perf_counter()
        state = self.agent.run(email, prefs, want_draft=False)
        latency = int((time.perf_counter() - start) * 1000)
        if state.error:
            self.actions.record("analyze_email", email.id, {"error": state.error}, success=False, latency_ms=latency)
            raise AnalysisFailed(state.error)
        data = dict(
            category=state.category.value, category_confidence=state.category_confidence, uncertain=state.uncertain,
            category_reason=state.analysis.category_reason, priority=state.priority.value,
            priority_reason=state.analysis.priority_reason, summary=state.summary,
            key_points=state.analysis.key_points, action_required=state.action_required,
            action_items=state.action_items, deadline_text=state.deadline_text, deadline_date=state.deadline_date,
            deadline_time=state.deadline_time, meeting_details=state.meeting_details,
            extracted_entities=state.extracted_entities, reply_required=state.reply_required,
            injection_flagged=state.injection_flagged, model=self.agent.llm.name,
        )
        if email.analysis:
            for k, v in data.items():
                setattr(email.analysis, k, v)
        else:
            email.analysis = EmailAnalysis(**data)
        self.db.commit()
        self.actions.record("analyze_email", email.id,
                            {"category": data["category"], "priority": data["priority"],
                             "injection_flagged": data["injection_flagged"]}, latency_ms=latency)
        return email

    def analyze_pending(self) -> tuple[int, int]:
        ok = failed = 0
        for e in self.emails.unanalyzed():
            try:
                self.analyze(e.id)
                ok += 1
            except AnalysisFailed:
                failed += 1
        return ok, failed

    def dashboard(self, today: date | None = None) -> dict:
        today = today or date.today()
        all_emails = self.emails.list()
        analyzed = [e for e in all_emails if e.analysis]
        important = [e for e in analyzed if e.analysis.priority in ("urgent", "high")]
        action = [e for e in analyzed if e.analysis.action_required]
        drafts = DraftRepository(self.db, self.user_id)
        deadlines = self.emails.upcoming_deadlines(today)
        return {
            "stats": {
                "total_emails": len(all_emails),
                "analyzed": len(analyzed),
                "unanalyzed": len(all_emails) - len(analyzed),
                "important": len(important),
                "urgent": sum(1 for e in analyzed if e.analysis.priority == "urgent"),
                "action_required": len(action),
                "pending_replies": drafts.count("draft", "approved"),
                "upcoming_deadlines": len(deadlines),
            },
            "recent_important": important[:5],
            "action_required": action[:5],
            "upcoming_deadlines": deadlines[:5],
        }
