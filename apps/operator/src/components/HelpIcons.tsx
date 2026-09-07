// Iconos SVG propios para AYUDA (batería, cobro, seguridad, otro): no dependen de la fuente de emojis del teléfono,
// que en algunos Android/WebView no existe y muestra cuadros. Carrito y Producto usan las imágenes de /public.
import type { ReactNode } from 'react';

function Svg({ children, viewBox = '0 0 64 64', testId }: { children: ReactNode; viewBox?: string; testId: string }) {
  return (
    <svg className="ico help-svg" viewBox={viewBox} width="64" height="64" aria-hidden focusable="false" data-testid={testId}>
      {children}
    </svg>
  );
}

export function BatteryIcon() {
  return (
    <Svg testId="icon-battery">
      <rect x="22" y="8" width="20" height="6" rx="2" fill="#1a1000" />
      <rect x="14" y="14" width="36" height="44" rx="6" fill="#1a1000" />
      <rect x="18" y="18" width="28" height="36" rx="4" fill="#3ad35a" />
      <rect x="29" y="26" width="6" height="20" rx="1.5" fill="#fff" />
      <rect x="22" y="33" width="20" height="6" rx="1.5" fill="#fff" />
    </Svg>
  );
}

export function PaymentIcon() {
  return (
    <Svg testId="icon-payment">
      <rect x="6" y="14" width="52" height="36" rx="6" fill="#ffd54a" />
      <rect x="6" y="22" width="52" height="8" fill="#1d3557" />
      <rect x="12" y="36" width="20" height="6" rx="2" fill="#1d3557" />
      <rect x="38" y="36" width="12" height="6" rx="2" fill="#1d3557" opacity="0.6" />
    </Svg>
  );
}

export function SecurityIcon() {
  return (
    <Svg testId="icon-security">
      <path d="M32 6 L54 15 V30 C54 44 44 54 32 58 C20 54 10 44 10 30 V15 Z" fill="#fff" />
      <path d="M32 12 L49 19 V30 C49 41 41 49 32 52 C23 49 15 41 15 30 V19 Z" fill="#c62828" />
      <rect x="29" y="22" width="6" height="16" rx="2" fill="#fff" />
      <circle cx="32" cy="43" r="3.5" fill="#fff" />
    </Svg>
  );
}

export function OtherIcon() {
  return (
    <Svg testId="icon-other">
      <circle cx="32" cy="32" r="26" fill="#fff" />
      <path d="M23 25 C23 18 29 15 33 15 C39 15 43 19 43 24 C43 31 34 31 34 38" stroke="#5c5147" strokeWidth="6" strokeLinecap="round" fill="none" />
      <circle cx="34" cy="47" r="4" fill="#5c5147" />
    </Svg>
  );
}
