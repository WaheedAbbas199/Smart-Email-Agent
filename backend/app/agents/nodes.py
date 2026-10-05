"""LangGraph nodes. Nodes contain agent logic only; external I/O lives in ai/ and integrations.

Security: the agent graph has NO send/delete tool. Sending is a separate,
human-approved API action.
"""

import logging
import time
from datetime import timedelta

from app.ai.llm_base import LLMClient, LLMError
from app.ai.mock_llm import detect_injection
from app.ai.schemas import PRIORITY_ORDER, Category, Priority
from app.agents.state import EmailAgentState


logger = logging.getLogger(__name__)

QUIET = {
    Category.newsletter,
    Category.promotion,
    Category.spam,
}

LOW_CONFIDENCE = 0.6


def _payload(s: EmailAgentState) -> dict:
    return {
        "sender": s.sender,
        "recipients": s.recipients,
        "subject": s.subject,
        "body": s.body,
        "received_at": s.received_at.isoformat() if s.received_at else "",
    }


def normalize_email(state: EmailAgentState) -> dict:
    body = " ".join(
        state.body.replace("\r", "").split(" ")
    ).strip()

    subject = " ".join(
        state.subject.split()
    )

    return {
        "body": body,
        "subject": subject,
        "injection_flagged": detect_injection(
            f"{subject}\n{body}"
        ),
    }


def make_analyze_email(llm: LLMClient):
    def analyze_email(state: EmailAgentState) -> dict:
        start = time.perf_counter()

        try:
            result = llm.analyze_email(
                _payload(state),
                state.preferences,
                state.today,
            )

        except LLMError as exc:
            # Log the actual error and full traceback.
            # This is important for debugging Gemini/API/model issues.
            logger.exception(
                "analysis failed",
                extra={
                    "node": "analyze_email",
                    "success": False,
                    "error_type": type(exc).__name__,
                },
            )

            return {
                "error": str(exc),
            }

        except Exception as exc:
            # Catch unexpected errors too, so they are visible
            # instead of silently failing the agent.
            logger.exception(
                "unexpected analysis error",
                extra={
                    "node": "analyze_email",
                    "success": False,
                    "error_type": type(exc).__name__,
                },
            )

            return {
                "error": f"Unexpected analysis error: {exc}",
            }

        logger.info(
            "analysis ok",
            extra={
                "node": "analyze_email",
                "success": True,
                "latency_ms": int(
                    (time.perf_counter() - start) * 1000
                ),
            },
        )

        return {
            "analysis": result,
        }

    return analyze_email


def classify_email(state: EmailAgentState) -> dict:
    a = state.analysis

    category = a.category
    conf = a.category_confidence

    uncertain = (
        conf is not None
        and conf < LOW_CONFIDENCE
    )

    if state.injection_flagged and category not in QUIET:
        category = Category.spam
        uncertain = False

    return {
        "category": category,
        "category_confidence": conf,
        "uncertain": uncertain,
    }


def detect_priority(state: EmailAgentState) -> dict:
    a = state.analysis

    priority = a.priority
    reason = a.priority_reason

    rule = state.preferences.get(
        state.category.value
    )

    if (
        rule in Priority._value2member_map_
        and not state.injection_flagged
    ):
        priority = Priority(rule)

        reason = (
            f"Set to {rule} by your rule for "
            f"{state.category.value} emails."
        )

    imminent = (
        a.deadline_date is not None
        and a.deadline_date
        <= state.today + timedelta(days=1)
    )

    if (
        imminent
        and state.category not in QUIET
        and not state.injection_flagged
        and PRIORITY_ORDER[priority]
        < PRIORITY_ORDER[Priority.high]
    ):
        priority = Priority.high

        reason = (
            "Raised to high because a deadline "
            "is within 24 hours."
        )

    if state.injection_flagged:
        priority = Priority.low

        reason = (
            "Email contains instructions aimed "
            "at an AI assistant."
        )

    return {
        "priority": priority,
        "analysis": a.model_copy(
            update={
                "priority_reason": reason
            }
        ),
    }


def extract_actions(state: EmailAgentState) -> dict:
    a = state.analysis

    if (
        state.injection_flagged
        or state.category in QUIET
    ):
        return {
            "action_required": False,
            "action_items": [],
            "reply_required": False,
            "meeting_details": a.meeting_details,
            "extracted_entities": a.extracted_entities,
            "deadline_text": a.deadline_text,
            "deadline_date": a.deadline_date,
            "deadline_time": a.deadline_time,
        }

    items = [
        i.strip()
        for i in a.action_items
        if i.strip()
    ]

    return {
        "action_required": (
            a.action_required
            or bool(items)
        ),
        "action_items": items,
        "reply_required": a.reply_required,
        "deadline_text": a.deadline_text,
        "deadline_date": a.deadline_date,
        "deadline_time": a.deadline_time,
        "meeting_details": a.meeting_details,
        "extracted_entities": a.extracted_entities,
    }


def generate_summary(state: EmailAgentState) -> dict:
    summary = state.analysis.summary.strip()

    if not summary:
        summary = (
            state.subject or state.body
        )[:200]

    return {
        "summary": summary
    }


def decide_next_action(state: EmailAgentState) -> dict:
    return {
        "approval_status": (
            "pending_human_approval"
            if (
                state.want_draft
                and state.reply_required
            )
            else "not_required"
        )
    }


def make_generate_reply(llm: LLMClient):
    def generate_reply(state: EmailAgentState) -> dict:
        try:
            draft = llm.draft_reply(
                _payload(state),
                state.analysis.model_dump(
                    mode="json"
                ),
            )

        except LLMError as exc:
            logger.exception(
                "reply generation failed",
                extra={
                    "node": "generate_reply",
                    "success": False,
                    "error_type": type(exc).__name__,
                },
            )

            return {
                "error": str(exc),
                "approval_status": "not_required",
            }

        except Exception as exc:
            logger.exception(
                "unexpected reply generation error",
                extra={
                    "node": "generate_reply",
                    "success": False,
                    "error_type": type(exc).__name__,
                },
            )

            return {
                "error": f"Unexpected reply error: {exc}",
                "approval_status": "not_required",
            }

        return {
            "reply_draft": draft,
            "tool_result": {
                "tool": "create_draft",
                "status": "draft_created_not_sent",
            },
        }

    return generate_reply


def finalize(state: EmailAgentState) -> dict:
    return {
        "final_response": {
            "category": (
                state.category.value
                if state.category
                else None
            ),
            "priority": (
                state.priority.value
                if state.priority
                else None
            ),
            "action_required": state.action_required,
            "reply_required": state.reply_required,
            "approval_status": state.approval_status,
            "error": state.error,
        }
    }


def route_after_analyze(
    state: EmailAgentState,
) -> str:
    return (
        "finalize"
        if state.error
        else "classify_email"
    )


def route_after_decision(
    state: EmailAgentState,
) -> str:
    return (
        "generate_reply"
        if state.approval_status
        == "pending_human_approval"
        else "finalize"
    )