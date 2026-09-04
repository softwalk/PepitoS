"""Control Tower: resumen y briefing."""
from fastapi import APIRouter, Depends
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
def briefing(date: str | None = None, _: CurrentUser = Depends(require("control_tower.read")), db: Session = Depends(get_db)):
    return ct.briefing(db, parse_date(date))
