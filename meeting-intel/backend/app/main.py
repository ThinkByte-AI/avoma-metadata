import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routers import auth as auth_router
from app.api.routers import users as users_router
from app.auth.bootstrap import ensure_bootstrap_admin
from app.config import get_settings
from app.db import get_db, get_session_factory
from app.errors import install_error_handlers
from app.logging import RequestLogMiddleware, setup_logging

log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    if s.admin_email and s.admin_password:
        try:
            with get_session_factory()() as db:
                ensure_bootstrap_admin(db, s.admin_email, s.admin_password)
        except Exception:
            log.exception("could not create bootstrap admin")
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Meeting Intelligence API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.add_middleware(RequestLogMiddleware)
    app.include_router(auth_router.router)
    app.include_router(users_router.router)

    @app.get("/api/health", tags=["system"])
    def health(db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
        except Exception:
            log.exception("health check: database unavailable")
            return JSONResponse(status_code=503, content={"status": "degraded", "db": "error"})
        return {"status": "ok", "db": "ok"}

    return app


app = create_app()
