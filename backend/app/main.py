import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError

from app.agents.catalog import seed_catalog
from app.api import agents, approvals, auth, demo, payments, policies, reporting, shopping
from app.core.config import get_settings
from app.core.errors import ServiceError
from app.database.session import Base, SessionLocal, engine
from app.services.state_machine import InvalidTransition

log = logging.getLogger("trustloop")


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Local dev convenience for SQLite. Use `alembic upgrade head` for PostgreSQL/Supabase.
    if str(engine.url).startswith("sqlite"):
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        try:
            seed_catalog(db)
        except Exception:  # tables may not exist yet if migrations were not run
            log.warning("Catalog seed skipped: run `alembic upgrade head` first.")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="TRUSTLOOP AI API", version="0.1.0", lifespan=lifespan,
                  description="Trust & authorization layer between AI shopping agents and PayPal payments.")
    app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origin_list, allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH", "OPTIONS"], allow_headers=["Authorization", "Content-Type"])

    @app.exception_handler(ServiceError)
    async def _svc(_: Request, e: ServiceError):
        return JSONResponse(status_code=e.status_code, content={"error": e.code, "detail": e.message, **e.extra})

    @app.exception_handler(InvalidTransition)
    async def _inv(_: Request, e: InvalidTransition):
        return JSONResponse(status_code=409, content={"error": "invalid_transition", "detail": str(e)})

    @app.exception_handler(StaleDataError)
    async def _stale(_: Request, e: Exception):
        return JSONResponse(status_code=409, content={"error": "concurrent_modification", "detail": "Resource was modified concurrently; retry."})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, e: Exception):
        log.exception("unhandled error")
        return JSONResponse(status_code=500, content={"error": "internal_error", "detail": "Internal server error."})

    for r in (auth.router, agents.router, policies.router, shopping.router, approvals.router, payments.router, reporting.router, demo.router):
        app.include_router(r)

    @app.get("/api/health", tags=["meta"])
    def health():
        from app.agents import gemini
        s = get_settings()
        return {"status": "ok", "database": "sqlite" if str(engine.url).startswith("sqlite") else "postgresql",
                "gemini_configured": gemini.is_configured(), "gemini_model": s.gemini_model,
                "paypal_configured": bool(s.paypal_client_id and s.paypal_client_secret),
                "paypal_webhook_configured": bool(s.paypal_webhook_id)}

    return app


app = create_app()
