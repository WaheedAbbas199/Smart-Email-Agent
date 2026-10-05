
from fastapi import APIRouter, Depends, HTTPException, Query

from app.ai.llm_base import LLMError
from app.api.deps import get_email_service, get_reply_service
from app.api.schemas import DraftOut, DraftRequest, EmailOut
from app.integrations.provider import EmailProviderError
from app.services.email_service import AnalysisFailed, EmailService
from app.services.reply_service import ReplyError, ReplyService


router = APIRouter(prefix="/api/emails", tags=["emails"])


@router.get("")
def list_emails(
    filter: str = Query("all", max_length=30),
    q: str | None = Query(None, max_length=200),
    category: str | None = None,
    priority: str | None = None,
    svc: EmailService = Depends(get_email_service),
):
    rows = svc.emails.list(filter, q, category, priority)

    return {
        "items": [
            EmailOut.model_validate(e).model_dump(
                mode="json",
                exclude={"body"},
            )
            for e in rows
        ],
        "count": len(rows),
    }


@router.post("/sync")
def sync(
    svc: EmailService = Depends(get_email_service),
):
    try:
        new = svc.sync()

    except EmailProviderError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "provider_error",
                "message": str(exc),
            },
        )

    return {"new_emails": new}


@router.post("/analyze-pending")
def analyze_pending(
    svc: EmailService = Depends(get_email_service),
):
    ok, failed = svc.analyze_pending()

    return {
        "analyzed": ok,
        "failed": failed,
    }


@router.get("/{email_id}", response_model=EmailOut)
def get_email(
    email_id: int,
    svc: EmailService = Depends(get_email_service),
):
    email = svc.emails.get(email_id)

    if not email:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": "Email not found",
            },
        )

    return email


@router.post("/{email_id}/analyze", response_model=EmailOut)
def analyze(
    email_id: int,
    force: bool = True,
    svc: EmailService = Depends(get_email_service),
):
    try:
        return svc.analyze(email_id, force=force)

    except LookupError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": "Email not found",
            },
        )

    except AnalysisFailed as exc:
        message = str(exc)

        # Gemini quota / rate-limit error
        if "429" in message or "quota" in message.lower():
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "ai_quota_exceeded",
                    "message": (
                        "Gemini AI quota has been exceeded. "
                        "Please try again later or check your "
                        "Gemini API quota/billing."
                    ),
                },
            )

        # Other AI analysis errors
        raise HTTPException(
            status_code=502,
            detail={
                "code": "analysis_failed",
                "message": message,
            },
        )


@router.post("/{email_id}/draft-reply", response_model=DraftOut)
def draft_reply(
    email_id: int,
    body: DraftRequest | None = None,
    svc: ReplyService = Depends(get_reply_service),
):
    body = body or DraftRequest()

    try:
        return svc.create_or_regenerate(
            email_id,
            body.instructions,
            body.regenerate,
        )

    except LookupError:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "not_found",
                "message": "Email not found",
            },
        )

    except ReplyError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "reply_conflict",
                "message": str(exc),
            },
        )

    except LLMError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "llm_error",
                "message": str(exc),
            },
        )
