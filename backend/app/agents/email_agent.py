"""Facade over the compiled graph."""
from datetime import date

from app.agents.graph import build_graph
from app.agents.state import EmailAgentState
from app.ai.llm_base import LLMClient
from app.db.models import Email


class EmailAgent:
    def __init__(self, llm: LLMClient):
        self.llm = llm
        self._graph = build_graph(llm)

    def run(self, email: Email, preferences: dict[str, str], want_draft: bool = False,
            today: date | None = None) -> EmailAgentState:
        state = EmailAgentState(
            email_id=email.id, thread_id=email.thread_id, sender=email.sender,
            recipients=list(email.recipients or []), subject=email.subject, body=email.body,
            received_at=email.received_at, preferences=preferences,
            today=today or date.today(), want_draft=want_draft,
        )
        out = self._graph.invoke(state)
        return EmailAgentState.model_validate(out)
