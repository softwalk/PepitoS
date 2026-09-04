"""Puntos autorizados: importa el catálogo de ubicaciones (app/data/puntos_autorizados_cdmx.json) como `Point`.

Fuente: "Pepito_100_mejores_ubicaciones_CDMX.xlsx" (investigación 05-ago-2026). Sólo los puntos de este catálogo
(más los que el administrador dé de alta a mano) pueden asignarse a carritos. Idempotente: se identifica cada punto por
`meta.ranking`; si ya existe se actualiza la ficha pero NUNCA se pisan coordenadas ya verificadas en campo.

Las coordenadas del catálogo son aproximadas (`geo_verified=False`): la apertura las tolera con la geocerca del punto
(150 m) hasta que un administrador las valide (edita lat/lng o adopta el GPS de una apertura y marca "verificado").
Con `geo_verified=True` aplica la regla estricta `open_max_distance_m` (50 m).
"""
import json
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.org import Point, Zone
from app.services import audit
from app.services import settings as settings_svc

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "puntos_autorizados_cdmx.json"
META_KEYS = ("ranking", "alcaldia", "node_type", "score", "horario_sugerido", "afluencia", "afinidad", "contexto", "resguardo", "riesgo", "justificacion", "estrategia", "validacion", "fuente", "geo_source")


def load_catalog() -> dict:
    with DATA_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def _zone_for(db: Session, name: str, cache: dict[str, Zone]) -> Zone:
    if name in cache:
        return cache[name]
    z = db.query(Zone).filter(Zone.name == name).first()
    if z is None:
        z = Zone(name=name, is_active=True)
        db.add(z)
        db.flush()
    cache[name] = z
    return z


def import_authorized_points(db: Session, actor_id: uuid.UUID | None = None, *, activate: bool = True) -> dict:
    """Crea/actualiza los puntos del catálogo. Devuelve {created, updated, total, zones_created}."""
    cat = load_catalog()
    default_target = settings_svc.get_int(db, "daily_sales_target_default_cents")
    existing_by_rank = {int(p.meta.get("ranking")): p for p in db.query(Point).all() if p.meta and p.meta.get("ranking") is not None}
    existing_by_name = {p.name: p for p in db.query(Point).all()}
    zones: dict[str, Zone] = {}
    zones_before = db.query(Zone).count()
    created = updated = 0
    for row in cat["points"]:
        meta = {k: row.get(k) for k in META_KEYS if row.get(k) is not None}
        meta["source"] = cat.get("source")
        # Alcaldía compuesta ("Iztacalco / Venustiano Carranza") → primera como zona.
        zone = _zone_for(db, str(row["alcaldia"]).split("/")[0].strip(), zones)
        p = existing_by_rank.get(int(row["ranking"])) or existing_by_name.get(row["name"])
        if p is None:
            p = Point(
                name=row["name"], address=f"{row['alcaldia']} · {row['node_type']}", lat=row["lat"], lng=row["lng"],
                geofence_radius_m=150, zone_id=zone.id, open_time=row.get("open_time") or "08:00", close_time=row.get("close_time") or "18:00",
                daily_target_cents=default_target, daily_target_tx=60, is_active=activate, geo_verified=bool(row.get("geo_verified", False)), meta=meta,
            )
            db.add(p)
            created += 1
        else:
            p.meta = {**(p.meta or {}), **meta}
            if not p.geo_verified:  # coordenadas aproximadas: se pueden refrescar desde el catálogo
                p.lat, p.lng = row["lat"], row["lng"]
            if p.zone_id is None:
                p.zone_id = zone.id
            updated += 1
    db.flush()
    zones_created = db.query(Zone).count() - zones_before
    audit.log(db, actor_id=actor_id, action="points.import_authorized", entity="points", after={"created": created, "updated": updated, "zones_created": zones_created, "source": cat.get("source")}, reason="Catálogo de puntos autorizados")
    return {"created": created, "updated": updated, "total": len(cat["points"]), "zones_created": zones_created, "imported_at": utcnow().isoformat()}
