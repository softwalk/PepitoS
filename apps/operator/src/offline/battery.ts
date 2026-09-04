// Battery Status API (si el navegador la ofrece).
export interface BatteryInfo {
  pct: number;
  charging: boolean;
}

type BatteryManager = { level: number; charging: boolean; addEventListener: (t: string, f: () => void) => void };

async function manager(): Promise<BatteryManager | null> {
  const nav = navigator as Navigator & { getBattery?: () => Promise<BatteryManager> };
  if (typeof nav.getBattery !== 'function') return null;
  try {
    return await nav.getBattery();
  } catch {
    return null;
  }
}

export async function readBattery(): Promise<BatteryInfo | null> {
  const m = await manager();
  return m ? { pct: Math.round(m.level * 100), charging: m.charging } : null;
}

export function watchBattery(cb: (b: BatteryInfo | null) => void): () => void {
  let active = true;
  void manager().then((m) => {
    if (!active) return;
    if (!m) {
      cb(null);
      return;
    }
    const push = () => cb({ pct: Math.round(m.level * 100), charging: m.charging });
    push();
    m.addEventListener('levelchange', push);
    m.addEventListener('chargingchange', push);
  });
  return () => {
    active = false;
  };
}
