"""Control Tower: resumen y briefing."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, require
from app.core.timeutil import parse_date
from app.services import control_tower as ct

router = APIRouter(prefix="/v1/control-tower", tags=["control tower"])


@router.get("/summary")
def summary(date: str | None = None, _: CurrentUser = Depends(require("control_tower.read")), db: Session = Depends(get_db)):
    return ct.summary(db, parse_date(date))


@router.get("/briefing")
def briefing(date: str | None = None, limit: int = Query(8, ge=1, le=100), _: CurrentUser = Depends(require("control_tower.read")), db: Session = Depends(get_db)):
    """`limit`: número de decisiones (casos abiertos de mayor prioridad) a incluir; 8 por defecto."""
    return ct.briefing(db, parse_date(date), limit=limit)
