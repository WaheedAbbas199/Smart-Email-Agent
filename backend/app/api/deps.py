"""FastAPI dependencies wiring services together."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.agents.email_agent import EmailAgent
from app.db.database import get_db
from app.db.models import User
from app.integrations.provider import EmailProviderError
from app.security.auth import get_current_user
from app.services.email_service import EmailService
from app.services.provider_factory import get_provider
from app.services.reply_service import ReplyService


def get_agent(request: Request) -> EmailAgent:
    return request.app.state.agent


def _provider(db: Session, user: User):
    try:
        return get_provider(db, user.id)
    except EmailProviderError as exc:
        raise HTTPException(status_code=409, detail={"code": "no_email_account", "message": str(exc)})


def get_email_service(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                      agent: EmailAgent = Depends(get_agent)) -> EmailService:
    return EmailService(db, user.id, _provider(db, user), agent)


def get_reply_service(db: Session = Depends(get_db), user: User = Depends(get_current_user),
                      agent: EmailAgent = Depends(get_agent)) -> ReplyService:
    return ReplyService(db, user.id, user.email, _provider(db, user), agent)
