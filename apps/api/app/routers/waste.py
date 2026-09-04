"""Merma."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, require
from app.schemas.operator import WasteIn
from app.services import sync as cmd

router = APIRouter(prefix="/v1/waste", tags=["merma"])


@router.post("", status_code=201)
def create_waste(data: WasteIn, current: CurrentUser = Depends(require("waste.create")), db: Session = Depends(get_db)):
    res = cmd.cmd_waste(db, current, data)
    return JSONResponse(status_code=res.status_code, content=res.body)
