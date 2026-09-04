import { MapContainer, Marker, Popup, TileLayer, Polyline } from 'react-leaflet';
import L from 'leaflet';
import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import type { PointStatus, RouteStop } from '../types';
import { STATUS_LABEL, fmtTime, label, money } from '../lib/format';

const TILES = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

function pin(status: string) {
  return L.divIcon({ className: '', html: `<div class="marker-pin s-${status}"></div>`, iconSize: [22, 22], iconAnchor: [11, 22], popupAnchor: [0, -20] });
}
function num(n: number, severity: string) {
  return L.divIcon({ className: '', html: `<div class="marker-num sev-${severity}">${n}</div>`, iconSize: [26, 26], iconAnchor: [13, 13], popupAnchor: [0, -12] });
}

function bounds(coords: [number, number][]): L.LatLngBoundsExpression | undefined {
  if (!coords.length) return undefined;
  return L.latLngBounds(coords.map(([a, b]) => L.latLng(a, b))).pad(0.25);
}

export const MAP_LEGEND = [
  { key: 'open', color: '#1e8e3e' },
  { key: 'late', color: '#e69a00' },
  { key: 'offline', color: '#6c7a89' },
  { key: 'closed', color: '#1f6fbf' },
  { key: 'not_scheduled', color: '#c3ccd6' },
];

export function PointsMap({ points, mini = false }: { points: PointStatus[]; mini?: boolean }) {
  const coords = useMemo(() => points.map((p) => [p.point.lat, p.point.lng] as [number, number]), [points]);
  const b = bounds(coords);
  return (
    <div>
      <div className={`map ${mini ? 'mini' : ''}`}>
        <MapContainer bounds={b} center={b ? undefined : [19.4326, -99.1332]} zoom={b ? undefined : 12} scrollWheelZoom={false} style={{ height: '100%', width: '100%' }}>
          <TileLayer attribution={ATTR} url={TILES} />
          {points.map((p) => {
            const pos: [number, number] = p.last_gps ? [p.last_gps.lat, p.last_gps.lng] : [p.point.lat, p.point.lng];
            return (
              <Marker key={p.point.id} position={pos} icon={pin(p.status)}>
                <Popup>
                  <div className="popup">
                    <b>{p.point.name}</b>
                    <br />
                    Estado: {label(STATUS_LABEL, p.status)}
                    <br />
                    Operador: {p.operator?.name ?? '—'}
                    <br />
                    Apertura: {fmtTime(p.opened_at)} · Último GPS: {fmtTime(p.last_gps?.at)} {p.last_gps ? (p.last_gps.in_geofence ? '(en geocerca)' : '(FUERA de geocerca)') : ''}
                    <br />
                    Batería: {p.battery_pct ?? '—'}%
                    <br />
                    Ventas: {money(p.sales_cents, { decimals: 0 })} / {money(p.target_cents, { decimals: 0 })} · {p.tx} tx
                    <br />
                    Casos: {p.open_cases.urgent} urgentes · {p.open_cases.review} revisar
                    <br />
                    <Link to={`/excepciones?point_id=${p.point.id}`}>Ver casos</Link> · <Link to={`/supervisor/auditoria/${p.point.id}`}>Auditar</Link>
                  </div>
                </Popup>
              </Marker>
            );
          })}
        </MapContainer>
      </div>
      <div className="legend">
        {MAP_LEGEND.map((l) => (
          <span key={l.key} style={{ ['--c' as string]: l.color }}>
            {label(STATUS_LABEL, l.key)}
          </span>
        ))}
      </div>
    </div>
  );
}

export function RouteMap({ stops }: { stops: RouteStop[] }) {
  const coords = useMemo(() => stops.map((s) => [s.point.lat, s.point.lng] as [number, number]), [stops]);
  const b = bounds(coords);
  return (
    <div className="map mini">
      <MapContainer bounds={b} center={b ? undefined : [19.4326, -99.1332]} zoom={b ? undefined : 12} scrollWheelZoom={false} style={{ height: '100%', width: '100%' }}>
        <TileLayer attribution={ATTR} url={TILES} />
        {coords.length > 1 && <Polyline positions={coords} pathOptions={{ color: '#1f4e79', dashArray: '6 6', weight: 3 }} />}
        {stops.map((s) => (
          <Marker key={s.point.id} position={[s.point.lat, s.point.lng]} icon={num(s.order, s.severity)}>
            <Popup>
              <div className="popup">
                <b>
                  {s.order}. {s.point.name}
                </b>
                <br />
                {s.reason}
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
