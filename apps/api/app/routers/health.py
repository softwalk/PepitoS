from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db

router = APIRouter(prefix="/v1", tags=["salud"])


@router.get("/health")
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:  # noqa: BLE001
        db_status = "error"
    body = {"status": "ok" if db_status == "ok" else "degraded", "db": db_status, "version": settings.APP_VERSION}
    return JSONResponse(status_code=200 if db_status == "ok" else 503, content=body)
