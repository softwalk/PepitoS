"""Reglas configurables y ejecución del motor."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, client_ip, require
from app.core.errors import ApiError
from app.core.timeutil import iso, utcnow
from app.models.cases import Rule
from app.schemas.backoffice import RulePut
from app.services import audit
from app.services.rules_engine import run_rules

router = APIRouter(prefix="/v1/rules", tags=["reglas"])


def _ser(r: Rule) -> dict:
    return {"key": r.key, "name": r.name, "enabled": r.enabled, "params": r.params, "severity": r.severity, "updated_at": iso(r.updated_at)}


@router.get("")
def list_rules(_: CurrentUser = Depends(require("rules.read")), db: Session = Depends(get_db)):
    return [_ser(r) for r in db.query(Rule).order_by(Rule.key).all()]


@router.get("/{key}")
def get_rule(key: str, _: CurrentUser = Depends(require("rules.read")), db: Session = Depends(get_db)):
    r = db.get(Rule, key)
    if r is None:
        raise ApiError("NOT_FOUND", "Regla no encontrada")
    return _ser(r)


@router.put("/{key}")
def put_rule(key: str, data: RulePut, request: Request, current: CurrentUser = Depends(require("rules.update")), db: Session = Depends(get_db)):
    r = db.get(Rule, key)
    if r is None:
        raise ApiError("NOT_FOUND", "Regla no encontrada")
    before = _ser(r)
    if data.enabled is not None:
        r.enabled = data.enabled
    if data.params is not None:
        r.params = {**(r.params or {}), **data.params}
    if data.severity is not None:
        r.severity = data.severity
    r.updated_at = utcnow()
    audit.log(db, actor_id=current.id, action="rule.update", entity="rule", entity_id=None, before=before, after=_ser(r), reason=f"rule:{key}", ip=client_ip(request))
    db.commit()
    return _ser(r)


@router.post("/run")
def run_now(_: CurrentUser = Depends(require("rules.run", "rules.update")), db: Session = Depends(get_db)):
    return run_rules(db, utcnow())
