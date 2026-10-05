"""Chooses the email provider for a user: demo mailbox or Gmail (when connected and demo_mode is off)."""
from datetime import timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.database import utcnow
from app.db.repositories import TokenRepository
from app.integrations.demo import DemoProvider
from app.integrations.gmail import GmailProvider
from app.integrations.provider import EmailProvider, EmailProviderError
from app.security import crypto, oauth

_demo_singleton = DemoProvider()


def get_provider(db: Session, user_id: int) -> EmailProvider:
    settings = get_settings()
    if settings.demo_mode:
        return _demo_singleton
    token = TokenRepository(db, user_id).get()
    if not token:
        raise EmailProviderError("No email account connected. Connect Gmail in Settings or enable DEMO_MODE.")
    if token.expires_at and token.expires_at <= utcnow() + timedelta(seconds=30):
        if not token.refresh_token_enc:
            raise EmailProviderError("Gmail session expired; reconnect your account")
        try:
            fresh = oauth.refresh_access_token(crypto.decrypt(token.refresh_token_enc))
        except oauth.OAuthError as exc:
            raise EmailProviderError(str(exc)) from exc
        token.access_token_enc = crypto.encrypt(fresh["access_token"])
        token.expires_at = fresh["expires_at"]
        db.commit()
    return GmailProvider(crypto.decrypt(token.access_token_enc))
