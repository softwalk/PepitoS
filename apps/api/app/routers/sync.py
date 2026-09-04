"""Sincronización offline: procesa comandos en orden; un error no detiene los demás."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, client_ip, require
from app.schemas.operator import SyncBatchIn
from app.services.sync import execute_command

router = APIRouter(prefix="/v1/sync", tags=["sync"])


@router.post("/batch")
def batch(data: SyncBatchIn, request: Request, current: CurrentUser = Depends(require("sync.batch")), db: Session = Depends(get_db)):
    results = []
    for command in data.commands:
        results.append(execute_command(db, current, command, ip=client_ip(request)))
    return {"results": results}
