"""Supervisor: excepciones, ruta y auditorías."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import CurrentUser, require
from app.core.errors import ApiError
from app.core.timeutil import iso, local_today, utcnow
from app.models.cases import Action, Audit, Case
from app.models.ops import Shift
from app.models.org import Point, User
from app.schemas.backoffice import AuditIn
from app.services import audit as audit_log
from app.services import events
from app.services import evidence as evidence_svc
from app.services.cases import open_case_if_new, scope_cases_query, serialize_case
from app.services.cash import sales_summary
from app.services.control_tower import point_statuses, serialize_cases
from app.services.geo import haversine_m
from app.services.priority import priority_score
from app.services.settings import cash_thresholds

AUDIT_CHECK_LABELS = {
    "clean_ok": "limpieza", "uniform_ok": "uniforme", "product_ok": "producto", "display_ok": "exhibición",
    "prices_visible": "precios visibles", "cart_secure": "carrito seguro", "pos_ok": "POS",
}

router = APIRouter(prefix="/v1", tags=["supervisor"])


def _zone_filter(current: CurrentUser):
    return current.zone_id if current.role == "supervisor" else None


@router.get("/supervisor/exceptions")
def exceptions(current: CurrentUser = Depends(require("supervisor.read", "cases.read")), db: Session = Depends(get_db)):
    now = utcnow()
    cases = scope_cases_query(db, current).filter(Case.status.in_(("open", "in_progress"))).all()
    data = serialize_cases(cases, now)
    normal = [p for p in point_statuses(db, local_today(now), zone_id=_zone_filter(current), now=now)]
    return {
        "urgent": [c for c in data if c["severity"] == "urgent"],
        "review": [c for c in data if c["severity"] == "review"],
        "normal": normal,
        "normal_cases": [c for c in data if c["severity"] == "normal"],
    }


@router.get("/supervisor/route")
def route(current: CurrentUser = Depends(require("supervisor.read", "cases.read")), db: Session = Depends(get_db)):
    """Ruta sugerida: puntos con casos abiertos ordenados por priority_score; dentro de cada grupo de
    severidad se encadena por vecino más cercano (haversine)."""
    now = utcnow()
    cases = scope_cases_query(db, current).filter(Case.status.in_(("open", "in_progress")), Case.point_id.isnot(None)).all()
    by_point: dict = {}
    for c in cases:
        entry = by_point.setdefault(c.point_id, {"score": 0.0, "severity": "normal", "case_ids": [], "reasons": []})
        score = priority_score(c.severity, c.impact_score, c.opened_at, now)
        entry["score"] = max(entry["score"], score)
        entry["case_ids"].append(str(c.id))
        entry["reasons"].append(c.title)
        rank = {"urgent": 3, "review": 2, "normal": 1}
        if rank[c.severity] > rank[entry["severity"]]:
            entry["severity"] = c.severity
    points = {p.id: p for p in db.query(Point).filter(Point.id.in_(list(by_point.keys()))).all()} if by_point else {}
    stops = []
    order = 0
    last = None
    for sev in ("urgent", "review", "normal"):
        group = [(pid, e) for pid, e in by_point.items() if e["severity"] == sev and pid in points]
        group.sort(key=lambda x: x[1]["score"], reverse=True)
        remaining = group[:]
        while remaining:
            if last is None:
                pid, e = remaining.pop(0)
            else:
                idx = min(range(len(remaining)), key=lambda i: (haversine_m(last.lat, last.lng, points[remaining[i][0]].lat, points[remaining[i][0]].lng), -remaining[i][1]["score"]))
                pid, e = remaining.pop(idx)
            p = points[pid]
            order += 1
            stops.append({
                "order": order, "point": {"id": str(p.id), "name": p.display_name, "lat": p.lat, "lng": p.lng},
                "reason": "; ".join(e["reasons"][:3]), "severity": e["severity"], "priority_score": round(e["score"], 2),
                "case_ids": e["case_ids"], "distance_from_previous_m": int(haversine_m(last.lat, last.lng, p.lat, p.lng)) if last else 0,
            })
            last = p
    return {"date": local_today(now).isoformat(), "stops": stops}


@router.post("/audits", status_code=201)
def create_audit(data: AuditIn, current: CurrentUser = Depends(require("audits.create")), db: Session = Depends(get_db)):
    point = db.get(Point, data.point_id)
    if point is None:
        raise ApiError("NOT_FOUND", "Punto no encontrado")
    if current.role == "supervisor" and point.zone_id != current.zone_id:
        raise ApiError("FORBIDDEN", "El punto no pertenece a tu zona")
    shift = db.get(Shift, data.shift_id) if data.shift_id else db.query(Shift).filter(Shift.point_id == point.id, Shift.status == "open").first()
    now = utcnow()
    expected = sales_summary(db, shift.id)["cash_expected_cents"] if shift else None
    failed = [k for k, v in data.checklist.items() if not v]
    a = Audit(
        point_id=point.id, shift_id=shift.id if shift else None, auditor_id=current.id, checklist=data.checklist,
        cash_counted_cents=data.cash_counted_cents, cash_expected_cents=expected, notes=data.notes, photos=[],
        non_conformities=failed, performed_at=now,
    )
    db.add(a)
    db.flush()
    # Fotos → object storage (B4). En `audits.photos` sólo quedan referencias {evidence_id, key}.
    photos_in = data.photos or []
    stored = evidence_svc.store_photos(db, [p if isinstance(p, str) else p.base64 for p in photos_in], kind="audit", entity="audit", entity_id=a.id, uploaded_by=current.id, point_id=point.id, shift_id=a.shift_id, taken_at=now)
    keys = [None if isinstance(p, str) else p.key for p in photos_in]
    a.photos = [{"evidence_id": str(ev.id), "key": keys[i] if i < len(keys) else None} for i, ev in enumerate(stored)]
    case_ids = []
    if failed:
        c = open_case_if_new(
            db, rule_key="audit_nonconformity", point_id=point.id, shift_id=a.shift_id, severity="review",
            title=f"No conformidades en auditoría: {', '.join(AUDIT_CHECK_LABELS.get(k, k) for k in failed)}", description=data.notes or "", impact_score=5 * len(failed),
            source="supervisor", actor_id=current.id, payload={"audit_id": str(a.id), "failed": failed}, category="audit", dedupe_date=now,
        )
        if c is not None:
            c.dedupe_key = f"audit_nonconformity:{a.id}"
            case_ids.append(str(c.id))
    threshold, severe = cash_thresholds(db)  # mismos umbrales que el cierre (settings / rules.params)
    if data.cash_counted_cents is not None and expected is not None and abs(data.cash_counted_cents - expected) > threshold:
        diff = data.cash_counted_cents - expected
        c = open_case_if_new(
            db, rule_key="surprise_cash_count", point_id=point.id, shift_id=a.shift_id, severity="urgent" if abs(diff) > severe else "review",
            title=f"Arqueo sorpresa con diferencia de ${abs(diff) / 100:,.2f}", description=f"Esperado ${expected / 100:,.2f}, contado ${data.cash_counted_cents / 100:,.2f}",
            impact_score=min(abs(diff) / 100, 50), source="supervisor", actor_id=current.id, payload={"audit_id": str(a.id), "difference_cents": diff}, category="cash", dedupe_date=now,
        )
        if c is not None:
            c.dedupe_key = f"surprise_cash_count:{a.id}"
            case_ids.append(str(c.id))
    for ca in data.corrective_actions:
        if ca.owner_id and db.get(User, ca.owner_id) is None:
            raise ApiError("NOT_FOUND", "Responsable no encontrado")
        db.add(Action(audit_id=a.id, case_id=uuid.UUID(case_ids[0]) if case_ids else None, description=ca.description, owner_id=ca.owner_id, due_date=ca.due_date, created_by=current.id))
    events.emit(db, "AuditCompleted", actor_id=current.id, point_id=point.id, shift_id=a.shift_id, entity="audit", entity_id=a.id, payload={"failed": failed, "case_ids": case_ids, "cash_counted_cents": data.cash_counted_cents})
    audit_log.log(db, actor_id=current.id, action="audit.create", entity="audit", entity_id=a.id, after={"checklist": data.checklist, "failed": failed, "cash_counted_cents": data.cash_counted_cents}, reason=data.notes)
    db.commit()
    return {"audit_id": str(a.id), "case_ids": case_ids, "cash_expected_cents": expected, "evidence": evidence_svc.serialize_for(db, "audit", a.id)}


def serialize_audit(db: Session, a: Audit) -> dict:
    return {
        "id": str(a.id), "point_id": str(a.point_id), "shift_id": str(a.shift_id) if a.shift_id else None, "auditor_id": str(a.auditor_id),
        "checklist": a.checklist, "non_conformities": a.non_conformities, "cash_counted_cents": a.cash_counted_cents,
        "cash_expected_cents": a.cash_expected_cents, "notes": a.notes, "performed_at": iso(a.performed_at),
        "photos": a.photos, "evidence": evidence_svc.serialize_for(db, "audit", a.id),
    }


@router.get("/audits")
def list_audits(point_id: uuid.UUID | None = None, current: CurrentUser = Depends(require("audits.create", "reports.read")), db: Session = Depends(get_db)):
    q = db.query(Audit)
    if current.role == "supervisor":
        q = q.join(Point, Point.id == Audit.point_id).filter(Point.zone_id == current.zone_id)
    if point_id:
        q = q.filter(Audit.point_id == point_id)
    return [serialize_audit(db, a) for a in q.order_by(Audit.performed_at.desc()).limit(200).all()]


@router.get("/audits/{audit_id}")
def get_audit(audit_id: uuid.UUID, current: CurrentUser = Depends(require("audits.create", "reports.read")), db: Session = Depends(get_db)):
    a = db.get(Audit, audit_id)
    if a is None:
        raise ApiError("NOT_FOUND", "Auditoría no encontrada")
    if current.role == "supervisor":
        point = db.get(Point, a.point_id)
        if point is None or point.zone_id != current.zone_id:
            raise ApiError("FORBIDDEN", "El punto no pertenece a tu zona")
    return serialize_audit(db, a)
