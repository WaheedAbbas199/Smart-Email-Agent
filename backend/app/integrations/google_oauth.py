"""Google OAuth 2.0 authorization-code flow."""

import secrets
from datetime import timedelta
from urllib.parse import urlencode

import httpx

from app.config import get_settings
from app.db.database import utcnow


AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"

SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


class OAuthError(Exception):
    pass


def is_configured() -> bool:
    settings = get_settings()

    return bool(
        settings.google_client_id
        and settings.google_client_secret
    )


def new_state() -> str:
    """Generate a cryptographically secure OAuth state value."""

    return secrets.token_urlsafe(24)


def build_auth_url(state: str) -> str:
    """Build Google authorization URL."""

    settings = get_settings()

    if not is_configured():
        raise OAuthError(
            "Google OAuth is not configured. "
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET."
        )

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }

    return f"{AUTH_URL}?{urlencode(params)}"


def _token_request(
    data: dict,
    client: httpx.Client | None = None,
) -> dict:
    """Send request to Google's OAuth token endpoint."""

    own_client = client is None
    c = client or httpx.Client(timeout=15.0)

    try:
        try:
            response = c.post(
                TOKEN_URL,
                data=data,
            )
        except httpx.HTTPError as exc:
            raise OAuthError(
                f"OAuth network error: {type(exc).__name__}"
            ) from exc

        if response.status_code != 200:
            try:
                detail = response.json()
            except Exception:
                detail = response.text[:500]

            raise OAuthError(
                f"OAuth token endpoint error: "
                f"HTTP {response.status_code} - {detail}"
            )

        try:
            token_data = response.json()
        except ValueError as exc:
            raise OAuthError(
                "Google returned an invalid token response"
            ) from exc

        expires_in = int(
            token_data.get("expires_in", 3600)
        )

        token_data["expires_at"] = (
            utcnow()
            + timedelta(seconds=max(expires_in - 60, 0))
        )

        return token_data

    finally:
        if own_client:
            c.close()


def exchange_code(
    code: str,
    client: httpx.Client | None = None,
) -> dict:
    """Exchange Google authorization code for tokens."""

    settings = get_settings()

    return _token_request(
        {
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
        client,
    )


def refresh_access_token(
    refresh_token: str,
    client: httpx.Client | None = None,
) -> dict:
    """Refresh an expired Google access token."""

    settings = get_settings()

    return _token_request(
        {
            "refresh_token": refresh_token,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "grant_type": "refresh_token",
        },
        client,
    )


def fetch_userinfo(
    access_token: str,
    client: httpx.Client | None = None,
) -> dict:
    """Fetch Google account profile information."""

    own_client = client is None
    c = client or httpx.Client(timeout=15.0)

    try:
        try:
            response = c.get(
                USERINFO_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
            )
        except httpx.HTTPError as exc:
            raise OAuthError(
                f"Google profile network error: "
                f"{type(exc).__name__}"
            ) from exc

        if response.status_code != 200:
            raise OAuthError(
                "Could not fetch Google profile"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise OAuthError(
                "Google returned an invalid profile response"
            ) from exc

    finally:
        if own_client:
            c.close()