"""Google OAuth authentication routes."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from starlette.status import HTTP_302_FOUND

from app.config import get_settings
from app.db.database import get_db, utcnow
from app.db.models import OAuthToken, User
from app.integrations.google_oauth import (
    OAuthError,
    build_auth_url,
    exchange_code,
    fetch_userinfo,
    new_state,
)
from app.security import crypto


router = APIRouter(prefix="/api/auth", tags=["auth"])

logger = logging.getLogger("app.auth")


@router.get("/google/login")
def google_login(request: Request):
    """Start Google OAuth flow."""

    state = new_state()

    # Store OAuth state in the browser session.
    # This is used to protect against CSRF attacks.
    request.session["oauth_state"] = state

    try:
        auth_url = build_auth_url(state)
    except OAuthError as exc:
        logger.error("Google OAuth is not configured: %s", exc)

        raise HTTPException(
            status_code=503,
            detail={
                "code": "oauth_not_configured",
                "message": str(exc),
            },
        ) from exc

    return RedirectResponse(
        url=auth_url,
        status_code=HTTP_302_FOUND,
    )


@router.get("/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """Handle Google's OAuth callback."""

    # Google returned an OAuth error.
    if error:
        logger.warning(
            "Google OAuth denied",
            extra={"error": error},
        )

        raise HTTPException(
            status_code=400,
            detail={
                "code": "oauth_denied",
                "message": f"Google authorization was denied: {error}",
            },
        )

    # Google must return both code and state.
    if not code or not state:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "oauth_callback_invalid",
                "message": "Missing OAuth code or state",
            },
        )

    # ---------------------------------------------------------
    # Validate OAuth state
    # ---------------------------------------------------------

    expected_state = request.session.get("oauth_state")

    if not expected_state:
        logger.warning(
            "OAuth state missing from session",
        )

        raise HTTPException(
            status_code=400,
            detail={
                "code": "oauth_state_missing",
                "message": (
                    "OAuth session expired or browser session was lost. "
                    "Please start Google login again."
                ),
            },
        )

    if not secrets_compare(state, expected_state):
        logger.warning(
            "OAuth state mismatch",
        )

        request.session.pop("oauth_state", None)

        raise HTTPException(
            status_code=400,
            detail={
                "code": "oauth_state_invalid",
                "message": "Invalid OAuth state. Please start Google login again.",
            },
        )

    # State has been successfully validated.
    request.session.pop("oauth_state", None)

    # ---------------------------------------------------------
    # Exchange authorization code for Google tokens
    # ---------------------------------------------------------

    try:
        tokens = exchange_code(code)

        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_at = tokens.get("expires_at")

        if not access_token:
            raise OAuthError(
                "Google did not return an access token"
            )

        # Fetch Google account profile.
        profile = fetch_userinfo(access_token)

    except OAuthError as exc:
        logger.exception("Google OAuth failed")

        raise HTTPException(
            status_code=502,
            detail={
                "code": "oauth_failed",
                "message": str(exc),
            },
        ) from exc

    # ---------------------------------------------------------
    # Google profile
    # ---------------------------------------------------------

    google_email = profile.get("email")
    google_name = profile.get("name") or ""

    scope = " ".join(
        tokens.get("scope", "").split()
    )

    if not google_email:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "google_profile_invalid",
                "message": "Google account email was not returned",
            },
        )

    # ---------------------------------------------------------
    # Find or create local user
    # ---------------------------------------------------------

    user = (
        db.query(User)
        .filter(User.email == google_email)
        .first()
    )

    if not user:
        user = User(
            email=google_email,
            name=google_name,
        )

        db.add(user)
        db.flush()

    else:
        # Keep user's Google profile name updated.
        if google_name:
            user.name = google_name

    # ---------------------------------------------------------
    # Find existing OAuth token
    # ---------------------------------------------------------

    oauth_token = (
        db.query(OAuthToken)
        .filter(OAuthToken.user_id == user.id)
        .first()
    )

    # ---------------------------------------------------------
    # Encrypt Google tokens before database storage
    # ---------------------------------------------------------

    encrypted_access_token = crypto.encrypt(
        access_token
    )

    encrypted_refresh_token = None

    if refresh_token:
        encrypted_refresh_token = crypto.encrypt(
            refresh_token
        )

    if oauth_token:

        oauth_token.provider = "google"

        # Always replace access token with latest encrypted token.
        oauth_token.access_token_enc = encrypted_access_token

        # Google may not send refresh_token on every login.
        # Therefore, keep the existing encrypted refresh token
        # when Google does not return a new one.
        if encrypted_refresh_token:
            oauth_token.refresh_token_enc = (
                encrypted_refresh_token
            )

        if expires_at:
            oauth_token.expires_at = expires_at

        oauth_token.scope = scope
        oauth_token.updated_at = utcnow()

    else:

        oauth_token = OAuthToken(
            user_id=user.id,
            provider="google",
            access_token_enc=encrypted_access_token,
            refresh_token_enc=encrypted_refresh_token,
            expires_at=expires_at,
            scope=scope,
        )

        db.add(oauth_token)

    # Save user + OAuth token.
    db.commit()

    # ---------------------------------------------------------
    # Create authenticated browser session
    # ---------------------------------------------------------

    request.session["user_id"] = user.id

    logger.info(
        "Google OAuth login successful",
        extra={
            "user_id": user.id,
            "email": google_email,
        },
    )

    # ---------------------------------------------------------
    # Redirect to frontend
    # ---------------------------------------------------------

    settings = get_settings()

    frontend_url = settings.cors_origin_list[0]

    return RedirectResponse(
        url=f"{frontend_url}/",
        status_code=HTTP_302_FOUND,
    )


@router.post("/logout")
def logout(request: Request):
    """Clear authenticated browser session."""

    request.session.clear()

    return {
        "status": "ok",
        "message": "Logged out",
    }


@router.get("/me")
def current_user(
    request: Request,
    db: Session = Depends(get_db),
):
    """Return the currently authenticated Google user."""

    user_id = request.session.get("user_id")

    if not user_id:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "not_authenticated",
                "message": "Please login with Google",
            },
        )

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )

    if not user:
        request.session.clear()

        raise HTTPException(
            status_code=401,
            detail={
                "code": "user_not_found",
                "message": "User session is no longer valid",
            },
        )

    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
    }


def secrets_compare(value_a: str, value_b: str) -> bool:
    """Constant-time comparison for OAuth state values."""

    import secrets

    return secrets.compare_digest(
        value_a,
        value_b,
    )