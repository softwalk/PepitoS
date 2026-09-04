/** Distancia haversine en metros (misma fórmula que el servidor). */
export function haversineM(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const r = 6371000;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dphi = ((lat2 - lat1) * Math.PI) / 180;
  const dl = ((lng2 - lng1) * Math.PI) / 180;
  const a = Math.sin(dphi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

/** Tolerancia de apertura: regla estricta (50 m) sólo con coordenadas verificadas; si no, la geocerca del punto. */
export function openLimitM(point: { geofence_radius_m: number; geo_verified?: boolean }, openMaxDistanceM: number | undefined): number {
  return point.geo_verified === false ? point.geofence_radius_m : openMaxDistanceM ?? 50;
}
