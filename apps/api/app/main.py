"""PEPITO OS API — FastAPI."""
import logging
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import install_error_handlers
from app.routers import (
    admin,
    approvals,
    assets,
    auth,
    cases,
    control_tower,
    gps,
    health,
    help,
    inventory,
    me,
    reports,
    rules,
    sales,
    shifts,
    supervisor,
    sync,
    waste,
)
from app.services.rules_engine import run_rules_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pepito")

scheduler: BackgroundScheduler | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scheduler
    if settings.RUN_SCHEDULER:
        scheduler = BackgroundScheduler(timezone="UTC")
        scheduler.add_job(run_rules_job, "interval", seconds=settings.RULES_INTERVAL_SECONDS, id="rules_engine", max_instances=1, coalesce=True)
        scheduler.start()
        log.info("Motor de reglas programado cada %s s", settings.RULES_INTERVAL_SECONDS)
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)
        scheduler = None


def create_app() -> FastAPI:
    docs = not settings.is_production  # en producción no se exponen /docs, /redoc ni /openapi.json
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.CORS_ORIGINS != "*",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    for r in (health, auth, me, shifts, sales, waste, help, inventory, gps, sync, supervisor, cases, control_tower, rules, approvals, reports, assets, admin):
        app.include_router(r.router)
    return app


app = create_app()
