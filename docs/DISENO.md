# Sistema de diseño PEPITO OS (v2)

Dos superficies, un mismo lenguaje: **Operador** (PWA, calle, una mano, sol) y **Backoffice** (Control Tower, densidad de datos). Sin frameworks CSS: tokens en `:root` de cada `styles.css`.

## Tokens compartidos

| Token | Operador | Backoffice | Uso |
|---|---|---|---|
| Marca | `#E8590C` (`--brand`) | `#E8590C` (`--accent`) | Acción principal / CTA única por vista |
| Fondo | crema `#FAF5EC` | gris `#F3F5F8` | Superficie base |
| Tinta | `#17130F` | `#16202C` | Texto principal (≥ 12:1) |
| Atenuado | `#5C544B` | `#5B6B7D` | Texto secundario (≥ 5.5:1 → AA) |
| Verde / Ámbar / Rojo / Azul | `#1A7F46` / `#8A5A00` texto · `#D98A00` relleno / `#B3261E` / `#1A56B3` | idem (`--amber-fill: #E0951A`) | Semáforo: texto oscuro sobre `*-bg`, relleno claro sólo en fondos sólidos |
| Radios | 10 / 14 / 18 / 24 px | 10 / 14 px | Cuanto más táctil, más redondo |
| Foco | anillo azul doble (`--focus`) | idem | `:focus-visible` en todo control |

Regla de color: **un color = un significado**. Verde = abierto/OK/efectivo, ámbar = pendiente/revisar/cerrar, rojo = urgente/error, azul = digital (QR) / ayuda, naranja = vender / acción de marca.

## Operador

- **Tira de estado** bajo el encabezado: su fondo cambia con la sincronía (verde guardado, ámbar pendiente con punto que late, rojo requiere ayuda, gris sin señal). Se lee sin mirar el texto.
- **Home = una acción principal.** Puesto cerrado → ABRIR PUESTO como héroe; abierto → VENDER. Los botones deshabilitados dicen por qué (`.btn-hint`). La `shift-card` resume estado, hora y ventas.
- **Vender:** control segmentado Efectivo / QR (siempre visible, vuelve a efectivo tras cada venta digital); botones de producto con relieve (`box-shadow 0 5px 0`) que se hunden al pulsar; toast con *Deshacer* 60 s.
- Objetivos táctiles: `--btn-h` 64 px (76 en texto grande), `--tap` 56 px. `html.large-text` escala todo.
- Checklists: la fila cambia de borde/fondo al responder (`.is-yes` / `.is-no`) y hay barra de progreso n/N.
- Sin fuentes externas (offline-first): `system-ui` con `tabular-nums`.

## Backoffice

- **Sidebar oscuro** (`#14213D`) con navegación agrupada por intención: Monitoreo → Campo → Negocio → Sistema. Activo = acento naranja en el borde. En móvil es un *drawer* (botón ☰, cierra con Escape, `inert` cuando está oculto) y además hay barra inferior con 4 accesos (supervisor: los marcados `mobile`; otros roles: los 4 primeros).
- **KPIs**: 6 en una fila a ≥ 1200 px; barra lateral de color por semáforo; excepciones abiertas como tres contadores clicables.
- **Tablas**: encabezado sticky, hover, numéricos alineados a la derecha, acciones como botones pequeños (`.row-actions`).
- **Iconos**: SVG inline en `components/icons.tsx` (`<Icon name="flag" />`), heredan `currentColor`.
- Texto blanco sobre naranja sólo en tamaño grande; en 12–14 px usar `--accent-dark`/`--brand-dark` o una cápsula oscura (`.sale-btn .btn-sub`). Ámbar sólido siempre con texto oscuro.
- Un solo botón naranja por pantalla (la acción que cambia el estado del sistema, p. ej. *Ejecutar reglas ahora*); el resto en `--primary` o neutro.

## Verificación

- `npx vitest run` en ambas apps.
- Smoke E2E con API real: `scripts/smoke.py` en cada app (ver README de cada una). Selectores que **no** deben cambiar: textos de los botones principales, `.sale-btn`, `.big-money`, `.numpad button[aria-label]`, `aside >> text=…`, `.bottom-nav`, `data-testid` existentes.
