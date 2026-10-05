"""FastAPI application entrypoint."""

import logging
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.agents.email_agent import EmailAgent
from app.ai.factory import create_llm
from app.api import (
    auth,
    dashboard,
    emails,
    replies,
    settings as settings_api,
)
from app.config import get_settings
from app.db.database import Base, SessionLocal, engine
from app.logging_config import request_id_var, setup_logging
from app.security.auth import get_or_create_local_user


logger = logging.getLogger("app")

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend"


class RateLimiter:
    """In-memory sliding window per client IP.

    Replace with Redis for multi-process deployments.
    """

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        q = self.hits[key]

        while q and now - q[0] > 60:
            q.popleft()

        if len(q) >= self.per_minute:
            return False

        q.append(now)
        return True


def create_app() -> FastAPI:
    cfg = get_settings()

    setup_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Initialize database tables.
        # The current SQLAlchemy engine is synchronous.
        Base.metadata.create_all(bind=engine)

        # Create/get local development user.
        with SessionLocal() as db:
            get_or_create_local_user(db)

        # Initialize AI agent.
        app.state.agent = EmailAgent(create_llm(cfg))

        logger.info(
            "startup complete",
            extra={"status": app.state.agent.llm.name},
        )

        # Seed demo data when demo mode is enabled.
        if cfg.demo_mode:
            _seed_demo(app)

        yield

    app = FastAPI(
        title="Smart Email Agent",
        version="1.0.0",
        lifespan=lifespan,
    )

    # ---------------------------------------------------------
    # Session middleware
    # ---------------------------------------------------------
    #
    # Used by Google OAuth to securely store:
    # - OAuth state
    # - authenticated user_id
    #
    # TOKEN_ENCRYPTION_KEY is currently used as the session secret.
    # Later, we can add a separate SESSION_SECRET_KEY.
    #
    session_secret = (
        cfg.token_encryption_key
        or "development-only-change-this-secret"
    )

    app.add_middleware(
        SessionMiddleware,
        secret_key=session_secret,
        https_only=cfg.app_env == "production",
        same_site="lax",
    )

    # ---------------------------------------------------------
    # Rate limiter
    # ---------------------------------------------------------

    app.state.limiter = RateLimiter(cfg.rate_limit_per_minute)

    # ---------------------------------------------------------
    # CORS
    # ---------------------------------------------------------

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
        allow_credentials=True,
    )

    # ---------------------------------------------------------
    # Request middleware
    # ---------------------------------------------------------

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]

        token = request_id_var.set(rid)
        start = time.perf_counter()

        try:
            if request.url.path.startswith("/api") and not app.state.limiter.allow(
                request.client.host if request.client else "?"
            ):
                return JSONResponse(
                    {
                        "error": {
                            "code": "rate_limited",
                            "message": "Too many requests",
                        }
                    },
                    status_code=429,
                )

            response = await call_next(request)

            response.headers["X-Request-ID"] = rid
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"

            if request.url.path.startswith("/api"):
                logger.info(
                    "request",
                    extra={
                        "path": request.url.path,
                        "status": response.status_code,
                        "latency_ms": int(
                            (time.perf_counter() - start) * 1000
                        ),
                    },
                )

            return response

        finally:
            request_id_var.reset(token)

    # ---------------------------------------------------------
    # HTTP exception handler
    # ---------------------------------------------------------

    @app.exception_handler(HTTPException)
    async def http_exc(_: Request, exc: HTTPException):
        detail = (
            exc.detail
            if isinstance(exc.detail, dict)
            else {
                "code": "http_error",
                "message": str(exc.detail),
            }
        )

        return JSONResponse(
            {"error": detail},
            status_code=exc.status_code,
        )

    # ---------------------------------------------------------
    # Validation exception handler
    # ---------------------------------------------------------

    @app.exception_handler(RequestValidationError)
    async def validation_exc(
        _: Request,
        exc: RequestValidationError,
    ):
        return JSONResponse(
            {
                "error": {
                    "code": "validation_error",
                    "message": "Invalid request",
                    "fields": [
                        ".".join(str(p) for p in e["loc"])
                        for e in exc.errors()
                    ],
                }
            },
            status_code=422,
        )

    # ---------------------------------------------------------
    # Global exception handler
    # ---------------------------------------------------------

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        logger.exception("unhandled error")

        return JSONResponse(
            {
                "error": {
                    "code": "internal_error",
                    "message": "Something went wrong",
                }
            },
            status_code=500,
        )

    # ---------------------------------------------------------
    # Health check
    # ---------------------------------------------------------

    @app.get("/health", tags=["health"])
    def health():
        return {
            "status": "ok",
            "llm": app.state.agent.llm.name,
            "demo_mode": cfg.demo_mode,
        }

    # ---------------------------------------------------------
    # API routers
    # ---------------------------------------------------------

    for r in (
        auth.router,
        dashboard.router,
        emails.router,
        replies.router,
        settings_api.router,
    ):
        app.include_router(r)

    # ---------------------------------------------------------
    # Frontend
    # ---------------------------------------------------------

    if FRONTEND_DIR.exists():
        app.mount(
            "/",
            StaticFiles(
                directory=FRONTEND_DIR,
                html=True,
            ),
            name="frontend",
        )

    return app


def _seed_demo(app: FastAPI) -> None:
    """Load demo mailbox; analyse immediately only when using
    the offline mock LLM (no API cost).
    """

    from app.services.email_service import EmailService
    from app.services.provider_factory import get_provider

    with SessionLocal() as db:
        svc = EmailService(
            db,
            1,
            get_provider(db, 1),
            app.state.agent,
        )

        svc.sync()

        if app.state.agent.llm.name.startswith("mock"):
            svc.analyze_pending()


app = create_app()