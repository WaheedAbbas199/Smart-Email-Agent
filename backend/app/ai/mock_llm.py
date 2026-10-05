"""Offline heuristic LLM stand-in for demo mode and tests.

NOT a real model: it is a deterministic rule engine so the whole product (workflow, DB, UI,
approval flow) can run without an API key. Real analysis quality comes from GeminiClient.
"""
import re
from datetime import date, timedelta

from app.ai.llm_base import LLMClient
from app.ai.schemas import Category, EmailAnalysisResult, Priority

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
ACTION_RE = re.compile(r"\b(please|kindly|can you|could you|confirm|submit|send|reply|let me know|rsvp|update|resolve|fix|call)\b", re.I)
INJECTION_RE = re.compile(r"(ignore (all )?(previous|prior) instructions|disregard (the )?(above|previous)|you are now|system prompt|forward all (your )?emails)", re.I)
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.I)


def detect_injection(text: str) -> bool:
    return bool(INJECTION_RE.search(text or ""))


def parse_when(text: str, base: date) -> tuple[str | None, date | None, str | None]:
    """Return (phrase, date, 'HH:MM') using only explicit cues; never guesses."""
    lower = text.lower()
    phrase, found = None, None
    if re.search(r"\btoday\b|\btonight\b", lower):
        phrase, found = "today", base
    elif re.search(r"\btomorrow\b", lower):
        phrase, found = "tomorrow", base + timedelta(days=1)
    else:
        for i, day in enumerate(WEEKDAYS):
            if re.search(rf"\b{day}\b", lower):
                delta = (i - base.weekday()) % 7
                phrase, found = day.capitalize(), base + timedelta(days=delta)
                break
    t = TIME_RE.search(text)
    hhmm = None
    if t:
        h, m, ap = int(t.group(1)), int(t.group(2) or 0), t.group(3).lower()
        if 1 <= h <= 12:
            h = (h % 12) + (12 if ap == "pm" else 0)
            hhmm = f"{h:02d}:{m:02d}"
    return phrase, found, hhmm


def _sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [p.strip() for p in parts if len(p.strip()) > 3]


class MockLLM(LLMClient):
    name = "mock-heuristic"

    def analyze_email(self, payload: dict, preferences: dict, today: date) -> EmailAnalysisResult:
        subject, body = payload.get("subject", ""), payload.get("body", "")
        text = f"{subject}\n{body}"
        low = text.lower()
        received = today
        if payload.get("received_at"):
            try:
                received = date.fromisoformat(payload["received_at"][:10])
            except ValueError:
                pass

        if detect_injection(text):
            return EmailAnalysisResult(
                category=Category.spam, priority=Priority.low,
                category_reason="Email contains instructions aimed at an AI assistant.",
                priority_reason="Suspicious content with no legitimate request.",
                summary="Email contains instructions aimed at an AI assistant, which were ignored.",
                key_points=["Treated as untrusted content", "No action taken"],
            )

        cat, prio, reason = Category.other, Priority.low, "No strong signals found."
        if "interview" in low:
            cat, prio, reason = Category.job, Priority.high, "Contains an interview invitation."
        elif re.search(r"payment (has )?failed|declined|overdue|billing issue|invoice", low):
            cat, prio, reason = Category.finance, Priority.high, "Mentions a payment problem."
            if re.search(r"within \d+ hours|suspend|today|immediately", low):
                prio = Priority.urgent
        elif re.search(r"complaint|refund|unacceptable|disappointed|not working|still waiting", low):
            cat, prio, reason = Category.customer, Priority.high, "Customer reports a problem."
        elif re.search(r"\bmeeting\b|calendar invite|zoom|google meet|\bsync\b", low):
            cat, prio, reason = Category.meeting, Priority.medium, "Meeting-related email."
        elif re.search(r"% off|limited[- ]time|discount|sale ends|shop now", low):
            cat, prio, reason = Category.promotion, Priority.low, "Promotional offer."
        elif re.search(r"unsubscribe|newsletter|weekly digest|this week in", low):
            cat, prio, reason = Category.newsletter, Priority.low, "Looks like a newsletter."
        elif re.search(r"you('ve| have) won|claim your prize|crypto giveaway|wire transfer|lottery", low):
            cat, prio, reason = Category.spam, Priority.low, "Typical spam/scam wording."
        elif re.search(r"report|deadline|submit|project|review|deliverable", low):
            cat, prio, reason = Category.work, Priority.medium, "Work-related request."
        elif re.search(r"dinner|weekend|birthday|family|catch up|photos", low):
            cat, prio, reason = Category.personal, Priority.medium, "Personal conversation."

        quiet = cat in (Category.newsletter, Category.promotion, Category.spam)
        sentences = _sentences(body)
        action_sents = [s for s in sentences if ACTION_RE.search(s)] if not quiet else []
        action_required = bool(action_sents)
        phrase, d, hhmm = parse_when(text, received) if not quiet else (None, None, None)
        if action_required and phrase and prio in (Priority.medium, Priority.low):
            prio, reason = Priority.high, "Requires a response and contains a deadline."
        meeting = None
        if cat == Category.meeting and (d or hhmm):
            meeting = {"date": d.isoformat() if d else None, "time": hhmm}
        summary = " ".join(sentences[:2])[:240] or subject
        return EmailAnalysisResult(
            category=cat, category_confidence=None,  # heuristics give no honest probability
            category_reason=reason, priority=prio, priority_reason=reason,
            summary=summary, key_points=sentences[:3],
            action_required=action_required,
            action_items=[s[:140] for s in action_sents[:3]],
            deadline_text=phrase, deadline_date=d, deadline_time=hhmm, meeting_details=meeting,
            extracted_entities={
                "amounts": re.findall(r"[$€£]\s?\d[\d,]*(?:\.\d+)?", text),
                "emails": re.findall(r"[\w.+-]+@[\w-]+\.[\w.]+", body)[:5],
            },
            reply_required=action_required and cat not in (Category.notification,),
        )

    def draft_reply(self, payload: dict, analysis: dict, instructions: str | None = None) -> str:
        sender = payload.get("sender", "")
        name = re.sub(r"<.*?>", "", sender).strip().split(" ")[0] or "there"
        items = analysis.get("action_items") or []
        lines = [f"Hi {name},", "", f"Thank you for your email regarding \"{payload.get('subject', '')}\"."]
        if items:
            lines.append("I have noted your request and will follow up on it:")
            lines += [f"- {i}" for i in items[:3]]
        else:
            lines.append("I have received your message and will get back to you shortly.")
        if analysis.get("deadline_text"):
            lines.append(f"I am aware of the timing ({analysis['deadline_text']}).")
        if instructions:
            lines.append(instructions)
        lines += ["", "Best regards"]
        return "\n".join(lines)
