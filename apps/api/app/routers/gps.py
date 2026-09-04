"""Pings GPS."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, require
from app.schemas.operator import GpsBatchIn
from app.services import sync as cmd

router = APIRouter(prefix="/v1/gps", tags=["gps"])


@router.post("/pings")
def pings(data: GpsBatchIn, current: CurrentUser = Depends(require("gps.ping")), db: Session = Depends(get_db)):
    return cmd.cmd_gps(db, current, data)
