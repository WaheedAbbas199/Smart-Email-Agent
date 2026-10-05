"""Token encryption at rest (Fernet). Required in production."""
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings

logger = logging.getLogger(__name__)
_PLAIN = "plain:"


def _fernet() -> Fernet | None:
    key = get_settings().token_encryption_key
    return Fernet(key.encode()) if key else None


def encrypt(value: str) -> str:
    f = _fernet()
    if f is None:
        if get_settings().app_env == "production":
            raise RuntimeError("TOKEN_ENCRYPTION_KEY must be set in production")
        logger.warning("TOKEN_ENCRYPTION_KEY not set; storing token unencrypted (development only)")
        return _PLAIN + value
    return f.encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    if value.startswith(_PLAIN):
        return value[len(_PLAIN):]
    f = _fernet()
    if f is None:
        raise RuntimeError("TOKEN_ENCRYPTION_KEY missing; cannot decrypt stored token")
    try:
        return f.decrypt(value.encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("Stored token cannot be decrypted with the configured key") from exc
