
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.schemas import CATEGORIES, PRIORITIES, SettingsUpdate
from app.config import get_settings
from app.db.database import get_db
from app.db.models import OAuthToken, User
from app.db.repositories import ActionRepository, TokenRepository
from app.security import crypto, oauth
from app.security.auth import get_current_user
from app.services.preference_service import PreferenceError, PreferenceService


router = APIRouter(prefix="/api", tags=["settings"])


def _settings_payload(
    db: Session,
    user: User,
    request: Request,
) -> dict:

    cfg = get_settings()
    prefs = PreferenceService(db, user.id)

    return {
        "priority_rules": prefs.priority_rules(),

        "settings": {
            k: v == "true"
            for k, v in prefs.settings().items()
        },

        "categories": CATEGORIES,
        "priorities": PRIORITIES,

        "account": {
            "email": user.email,
            "name": user.name,
            "demo_mode": cfg.demo_mode,

            "gmail_connected": (
                TokenRepository(db, user.id).get() is not None
            ),

            "oauth_configured": oauth.is_configured(),

            "llm": request.app.state.agent.llm.name,
        },
    }


@router.get("/settings")
def get_settings_route(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _settings_payload(db, user, request)


@router.patch("/settings")
def patch_settings(
    body: SettingsUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        PreferenceService(db, user.id).update(
            body.priority_rules,
            body.settings,
        )

    except PreferenceError as exc:
        raise HTTPException(
            422,
            {
                "code": "invalid_preference",
                "message": str(exc),
            },
        )

    return _settings_payload(db, user, request)


@router.get("/actions")
def list_actions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = ActionRepository(db, user.id).recent()

    return {
        "items": [
            {
                "id": r.id,
                "action": r.action,
                "email_id": r.email_id,
                "success": r.success,
                "detail": r.detail,
                "latency_ms": r.latency_ms,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


# ============================================================
# GOOGLE OAUTH LOGIN
# ============================================================

@router.get("/auth/google/login")
def google_login():

    # Generate CSRF protection state
    state = oauth.new_state()

    try:
        # Build Google authorization URL
        url = oauth.build_auth_url(state)

    except oauth.OAuthError as exc:
        raise HTTPException(
            503,
            {
                "code": "oauth_not_configured",
                "message": str(exc),
            },
        )

    response = RedirectResponse(url)

    # Store OAuth state in browser cookie.
    #
    # IMPORTANT:
    # For local development:
    # secure=False
    #
    # path="/"
    # makes the cookie available to the callback endpoint:
    # /api/auth/google/callback
    #
    response.set_cookie(
        key="oauth_state",
        value=state,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=False,
        path="/",
    )

    return response


# ============================================================
# GOOGLE OAUTH CALLBACK
# ============================================================

@router.get("/auth/google/callback")
def google_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    # User denied Google permission
    if error:
        return RedirectResponse(
            "/settings.html?oauth=denied"
        )

    # Google did not return authorization code
    if not code:
        return RedirectResponse(
            "/settings.html?oauth=denied"
        )

    # --------------------------------------------------------
    # Validate OAuth state
    # --------------------------------------------------------

    saved_state = request.cookies.get("oauth_state")

    if not state:
        raise HTTPException(
            400,
            {
                "code": "invalid_state",
                "message": "OAuth state is missing from Google callback",
            },
        )

    if not saved_state:
        raise HTTPException(
            400,
            {
                "code": "invalid_state",
                "message": (
                    "OAuth state cookie is missing. "
                    "Please start Google login again."
                ),
            },
        )

    if state != saved_state:
        raise HTTPException(
            400,
            {
                "code": "invalid_state",
                "message": "OAuth state mismatch",
            },
        )

    # --------------------------------------------------------
    # Exchange authorization code for Google tokens
    # --------------------------------------------------------

    try:
        tok = oauth.exchange_code(code)

        info = oauth.fetch_userinfo(
            tok["access_token"]
        )

    except oauth.OAuthError as exc:
        raise HTTPException(
            502,
            {
                "code": "oauth_failed",
                "message": str(exc),
            },
        )

    # --------------------------------------------------------
    # Save OAuth token
    # --------------------------------------------------------

    row = (
        TokenRepository(db, user.id).get()
        or OAuthToken(
            user_id=user.id,
            access_token_enc="",
        )
    )

    row.access_token_enc = crypto.encrypt(
        tok["access_token"]
    )

    if tok.get("refresh_token"):
        row.refresh_token_enc = crypto.encrypt(
            tok["refresh_token"]
        )

    row.expires_at = tok["expires_at"]
    row.scope = tok.get("scope", "")

    # --------------------------------------------------------
    # Update local user with Google account information
    # --------------------------------------------------------

    if info.get("email"):
        user.email = info["email"]
        user.name = info.get(
            "name",
            user.name,
        )

    db.add(row)
    db.commit()

    # --------------------------------------------------------
    # Record successful connection
    # --------------------------------------------------------

    ActionRepository(db, user.id).record(
        "connect_gmail",
        detail={
            "email": user.email,
        },
    )

    # --------------------------------------------------------
    # Remove OAuth state cookie
    # --------------------------------------------------------

    response = RedirectResponse(
        "/settings.html?oauth=connected"
    )

    response.delete_cookie(
        key="oauth_state",
        path="/",
    )

    return response


# ============================================================
# DISCONNECT GOOGLE / GMAIL
# ============================================================

@router.post("/auth/disconnect")
def disconnect(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):

    row = TokenRepository(db, user.id).get()

    if row:
        db.delete(row)
        db.commit()

        ActionRepository(db, user.id).record(
            "disconnect_gmail"
        )

    return JSONResponse(
        {
            "disconnected": bool(row)
        }
    )
