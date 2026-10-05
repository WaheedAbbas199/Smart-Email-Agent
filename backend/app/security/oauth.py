"""Google OAuth 2.0 (authorization code flow). Tokens stay server-side; the browser never sees them."""
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.db.database import utcnow

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPES = ["openid", "email", "profile",
          "https://www.googleapis.com/auth/gmail.readonly",
          "https://www.googleapis.com/auth/gmail.send"]


class OAuthError(Exception):
    pass


def is_configured() -> bool:
    s = get_settings()
    return bool(s.google_client_id and s.google_client_secret)


def new_state() -> str:
    return secrets.token_urlsafe(24)


def build_auth_url(state: str) -> str:
    s = get_settings()
    if not is_configured():
        raise OAuthError("Google OAuth is not configured (set GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)")
    params = {"client_id": s.google_client_id, "redirect_uri": s.google_redirect_uri, "response_type": "code",
              "scope": " ".join(SCOPES), "access_type": "offline", "prompt": "consent", "state": state}
    return f"{AUTH_URL}?{urlencode(params)}"


def _token_request(data: dict, client: httpx.Client | None = None) -> dict:
    c = client or httpx.Client(timeout=15.0)
    try:
        resp = c.post(TOKEN_URL, data=data)
    except httpx.HTTPError as exc:
        raise OAuthError(f"OAuth network error: {type(exc).__name__}") from exc
    if resp.status_code != 200:
        raise OAuthError(f"OAuth token endpoint error: HTTP {resp.status_code}")
    tok = resp.json()
    tok["expires_at"] = utcnow() + timedelta(seconds=int(tok.get("expires_in", 3600)) - 60)
    return tok


def exchange_code(code: str, client: httpx.Client | None = None) -> dict:
    s = get_settings()
    return _token_request({"code": code, "client_id": s.google_client_id, "client_secret": s.google_client_secret,
                           "redirect_uri": s.google_redirect_uri, "grant_type": "authorization_code"}, client)


def refresh_access_token(refresh_token: str, client: httpx.Client | None = None) -> dict:
    s = get_settings()
    return _token_request({"refresh_token": refresh_token, "client_id": s.google_client_id,
                           "client_secret": s.google_client_secret, "grant_type": "refresh_token"}, client)


def fetch_userinfo(access_token: str, client: httpx.Client | None = None) -> dict:
    c = client or httpx.Client(timeout=15.0)
    resp = c.get(USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"})
    if resp.status_code != 200:
        raise OAuthError("Could not fetch Google profile")
    return resp.json()
