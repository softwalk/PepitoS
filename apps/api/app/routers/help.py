"""Botón NECESITO AYUDA."""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, require
from app.schemas.operator import HelpCaseIn
from app.services import sync as cmd

router = APIRouter(prefix="/v1/help-cases", tags=["ayuda"])


@router.post("", status_code=201)
def create_help_case(data: HelpCaseIn, current: CurrentUser = Depends(require("help.create")), db: Session = Depends(get_db)):
    res = cmd.cmd_help_case(db, current, data)
    return JSONResponse(status_code=res.status_code, content=res.body)
