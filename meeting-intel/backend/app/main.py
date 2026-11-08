import logging

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import install_error_handlers
from app.logging import RequestLogMiddleware, setup_logging

log = logging.getLogger("app")


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Meeting Intelligence API",
        version="0.1.0",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    install_error_handlers(app)
    app.add_middleware(RequestLogMiddleware)

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
