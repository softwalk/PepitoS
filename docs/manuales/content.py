# -*- coding: utf-8 -*-
from build import flow, semaforo, states, bars, fig

NAVY, ORANGE, GREEN, AMBER, RED, BLUE, GRAY = "#14213d", "#e8590c", "#1a7f46", "#e0951a", "#b3261e", "#1a56b3", "#5b6b7d"

# =====================================================================
# OPERADOR
# =====================================================================
OP_INTRO = """
<p>Eres quien vende en la calle. Tu app es la <b>PWA Operador</b> en tu teléfono: funciona sin señal y guarda todo hasta que vuelva la red. Con ella puedes:</p>
<div class="cards">
<div class="card"><h5>🔓 Abrir el puesto</h5><p>Checklist de 5 puntos (Sí/No), ubicación automática y, algunos días, una foto de muestreo.</p></div>
<div class="card"><h5>🛍️ Vender</h5><p>Un toque por venta: 50 g, 75 g o 100 g. Efectivo o QR/Tarjeta. Sabor opcional. Deshacer en 60 s.</p></div>
<div class="card"><h5>🗑️ Registrar merma</h5><p>Producto que se tira o regala: tamaño, cantidad y motivo.</p></div>
<div class="card"><h5>🆘 Pedir ayuda</h5><p>Carrito, batería, producto, cobro, seguridad (prioritaria) u otro con nota y foto.</p></div>
<div class="card"><h5>🔒 Cerrar el puesto</h5><p>Cuenta el efectivo, cuenta el producto, checklist de salida. El sistema concilia.</p></div>
<div class="card"><h5>⚙️ Ajustes</h5><p>Ver estado del GPS y de lo pendiente de enviar, audio, texto grande, cerrar sesión.</p></div>
</div>
<div class="callout">Lo que <b>no</b> puedes hacer: entrar al backoffice (te dirá <i>"Este acceso es para supervisores y backoffice. Usa la app de operador."</i>), cambiar precios, cancelar ventas de otros ni reabrir un turno cerrado (eso lo hace el administrador).</div>
""" + fig(flow([("Entrar", "usuario y contraseña", NAVY), ("ABRIR PUESTO", "checklist + GPS (+ foto)", GREEN), ("VENDER", "un toque por venta", ORANGE), ("NECESITO AYUDA", "cuando haga falta", BLUE), ("CERRAR PUESTO", "efectivo · producto · checklist", AMBER)]), "Tu jornada en cinco pasos. La barra superior siempre muestra tu punto, tu carrito, si lo tuyo ya se envió, el GPS y la batería.")

OP_QUICK = """
<div class="cards">
<div class="card"><h5><span class="n">1</span>Entra</h5><p>Abre la app desde el icono de tu pantalla de inicio (<b>https://</b>). Escribe usuario y contraseña → <span class="ui p">ENTRAR</span>. Verás "Bienvenido" con tu punto y carrito.</p></div>
<div class="card"><h5><span class="n">2</span>Abre el puesto</h5><p><span class="ui g">ABRIR PUESTO</span> → marca Sí/No en los 5 puntos → <span class="ui g">LISTO</span>. Si hoy toca foto: <span class="ui b">TOMAR FOTO</span>.</p></div>
<div class="card"><h5><span class="n">3</span>Vende</h5><p>Elige forma de pago (Efectivo / QR) y toca el tamaño. Verás "✓ Venta registrada". Si te equivocaste: <span class="ui">↩ Deshacer</span> (60 s).</p></div>
<div class="card"><h5><span class="n">4</span>Si algo pasa</h5><p><span class="ui b">NECESITO AYUDA</span> y toca la categoría. Seguridad se envía de inmediato.</p></div>
<div class="card"><h5><span class="n">5</span>Cierra</h5><p><span class="ui a">CERRAR PUESTO</span> → escribe cuánto efectivo tienes → cuenta producto → checklist de salida → <span class="ui a">CERRAR PUESTO</span> → <span class="ui">Terminar</span>.</p></div>
<div class="card"><h5><span class="n">6</span>Revisa la barra</h5><p>"✓ Guardado" = todo enviado. "Pendiente de enviar (n)" = se enviará solo cuando haya señal. "Requiere ayuda" = avisa al supervisor.</p></div>
</div>
<h3 id="op-barra">La barra superior</h3>
<div class="tbl"><table><tr><th>Lo que ves</th><th>Significa</th><th>Qué hacer</th></tr>
<tr><td><span class="badge b-green">✓ Guardado</span></td><td>Todo lo que hiciste ya está en el servidor.</td><td>Nada.</td></tr>
<tr><td><span class="badge b-amber">Pendiente de enviar (3)</span></td><td>Hay 3 registros guardados en el teléfono esperando red. La tira se pone ámbar.</td><td>Sigue trabajando; se envían solos. No cierres sesión.</td></tr>
<tr><td><span class="badge b-red">Requiere ayuda</span></td><td>Algún registro fue rechazado por el servidor.</td><td>Ajustes → <span class="ui">Reintentar enviar</span>; si persiste, avisa al supervisor.</td></tr>
<tr><td><span class="badge b-gray">📴 Sin señal</span></td><td>El teléfono no tiene internet.</td><td>Puedes vender, cerrar y pedir ayuda igual; se envía después.</td></tr>
<tr><td><span class="badge b-red">📡 Sin GPS</span></td><td>La app no consigue tu ubicación.</td><td>Tócala: te lleva a Ajustes y te dice la causa y la solución.</td></tr>
<tr><td><span class="badge b-amber">🔋 22%</span></td><td>Batería del teléfono baja (ámbar ≤ 25 %, rojo ≤ 10 %).</td><td>Conecta el cargador; el supervisor también lo ve.</td></tr>
</table></div>
"""

OP_DETAIL = """
<h3 id="op-login">Entrar y cambio de contraseña</h3>
<p>Pantalla con el logo, <b>Usuario</b> y <b>Contraseña</b>. Mensajes posibles: <i>"Usuario o contraseña incorrectos"</i>, <i>"No hay señal. Conéctate para iniciar sesión."</i> (la primera vez necesitas internet), <i>"Este teléfono fue dado de baja. Avisa a tu supervisor."</i> y, tras varios intentos fallidos, <i>"Demasiados intentos. Espera N minutos"</i> con cuenta regresiva.</p>
<p>Si el administrador te restableció la contraseña, la app te pedirá cambiarla antes de seguir: contraseña actual, nueva (mínimo 8 caracteres) y repetirla → <span class="ui p">GUARDAR CONTRASEÑA</span>.</p>

<h3 id="op-home">Inicio</h3>
<p>Una tarjeta te dice en qué estás: <b>Puesto cerrado</b> (con tu horario), <b>Puesto abierto</b> (desde qué hora, cuántas ventas y cuánto llevas), <b>Abierto, pendiente de enviar</b> (abriste sin señal), <b>Turno de hoy terminado</b> o <b>No tienes punto asignado hoy</b>. Debajo, el botón grande es la acción que toca ahora; los botones apagados explican por qué (<i>"Abre el puesto primero"</i>, <i>"Turno terminado"</i>, <i>"Sin asignación"</i>).</p>

<h3 id="op-abrir">Abrir puesto</h3>
<p>La app busca tu ubicación mientras contestas (<i>"Buscando ubicación…"</i> → <i>"Ubicación lista (±12 m)"</i>). Si no la consigue, verás la causa y qué hacer; <b>puedes abrir igual</b>: el supervisor lo verá como pendiente.</p>
<div class="tbl"><table><tr><th>Pregunta</th><th>Si contestas No…</th><th>Qué pasa</th></tr>
<tr><td>🔐 Carrito asegurado</td><td>Crítico</td><td>Se abre un caso <b>URGENTE</b> para el supervisor: <i>"Carrito no asegurado: revisa candado y resguardo"</i>.</td></tr>
<tr><td>🔋 Batería cargada</td><td>Crítico</td><td>Caso REVISAR: <i>"conecta el cargador o pide reemplazo"</i>.</td></tr>
<tr><td>Producto suficiente y en buen estado</td><td>Crítico</td><td>Caso REVISAR: <i>"pide reposición"</i>.</td></tr>
<tr><td>🧽 Carrito limpio</td><td>No crítico</td><td>Queda anotado; se te pide limpiar antes de vender.</td></tr>
<tr><td>💳 Terminal POS funciona</td><td>Crítico</td><td>Caso REVISAR: <i>"cobra sólo en efectivo y pide ayuda"</i>.</td></tr>
</table></div>
<p>Con todo en Sí → <b>"LISTO PARA VENDER"</b>. Con algún No crítico → <b>"ABIERTO CON PENDIENTES"</b>, la lista de lo que falta y <i>"Ya avisamos al supervisor"</i>; puedes vender de todos modos. Si estás lejos de tu punto (fuera de la geocerca, 150 m normalmente) aparece <i>"Estás fuera del punto asignado"</i>.</p>
<p><b>Foto de muestreo.</b> Algunos días (10 % de las aperturas, lo decide el sistema) el botón dice <span class="ui g">SIGUIENTE: FOTO</span>: toma una foto del puesto listo. Si la cámara falla, <span class="ui">Continuar sin foto</span>; nunca te bloquea. Ese mismo día también se pide foto al cerrar.</p>

<h3 id="op-vender">Vender</h3>
<p>Arriba: <b>Ventas del turno</b> y <b>Total</b>. Luego la forma de pago (<span class="ui g">💵 Efectivo</span> | <span class="ui b">📱 QR / Tarjeta</span>) y un botón grande por tamaño con su precio. La forma de pago digital vuelve sola a Efectivo después de cada venta, para que no se te quede pegada.</p>
<div class="tbl"><table><tr><th>Acción</th><th>Cómo</th><th>Límite</th></tr>
<tr><td>Venta</td><td>Toca el tamaño. Toast <i>"✓ Venta registrada · 100 g · $45"</i> y la voz lo repite si tienes audio.</td><td>—</td></tr>
<tr><td>Sabor</td><td>Abre <i>"🌶️ Sabor (opcional)"</i> y elige un chip; se aplica a la siguiente venta.</td><td>Se limpia tras cada venta.</td></tr>
<tr><td>Deshacer</td><td><span class="ui">↩ Deshacer</span> en el toast.</td><td>60 s. Si la venta ya se envió, te pide motivo: <i>Me equivoqué · Cliente se fue · Cambio de tamaño</i> (hasta 5 min después). Pasado ese tiempo sólo el supervisor puede cancelarla.</td></tr>
<tr><td>Merma</td><td><span class="ui">🗑️ MERMA</span> → tamaño → cuántas (1, 2, 3 o +) → motivo (derrame, calidad, caducado, muestra, otro).</td><td>Cuenta para el indicador de merma del punto (más de 4 % abre un caso).</td></tr>
</table></div>

<h3 id="op-ayuda">Necesito ayuda</h3>
<div class="tbl"><table><tr><th>Botón</th><th>Prioridad para el supervisor</th><th>Detalle</th></tr>
<tr><td>🚨 Seguridad</td><td><span class="badge b-red">URGENTE</span></td><td>Se envía de inmediato (espera GPS máximo 3 s). Mensaje: <i>"Mantente a salvo. Ayuda prioritaria en camino."</i></td></tr>
<tr><td>🔋 Batería · 💳 Cobro</td><td><span class="badge b-amber">REVISAR</span></td><td>Impacto alto.</td></tr>
<tr><td>Carrito · Producto</td><td><span class="badge b-amber">REVISAR</span></td><td>—</td></tr>
<tr><td>❓ Otro</td><td><span class="badge b-green">NORMAL</span></td><td>Puedes escribir una nota (280 caracteres) y adjuntar foto. El sistema sugiere una categoría al supervisor.</td></tr>
</table></div>

<h3 id="op-cerrar">Cerrar puesto</h3>
""" + fig(flow([("1 · Efectivo", "Debes tener $X · Tengo: teclado", AMBER), ("2 · Producto", "cuántas quedan por tamaño", AMBER), ("3 · Antes de irte", "checklist Sí/No", AMBER), ("4 · Foto", "sólo días de muestreo", GRAY), ("Resultado", "Conciliado o Diferencia", GREEN)]), "Los pasos del cierre. El paso 4 sólo aparece los días en que también se pidió foto al abrir.") + """
<p><b>"Debes tener"</b> es el efectivo esperado: ventas en efectivo del turno (las digitales no cuentan). Escribe lo que contaste y <span class="ui p">CONTINUAR</span>. Si estás sin señal, el monto se calcula en tu teléfono (<i>"calculado en el teléfono"</i>) y el servidor confirma después.</p>
<div class="tbl"><table><tr><th>Resultado</th><th>Cuándo</th><th>Qué sigue</th></tr>
<tr><td>✅ Cierre conciliado</td><td>Diferencia de ±$20 o menos (parámetro del administrador).</td><td>Nada. <i>"Buen trabajo."</i></td></tr>
<tr><td>📋 Se registró una diferencia</td><td>Más de $20 de diferencia.</td><td>Se abre un caso para el supervisor. Más de $100: caso urgente y Finanzas debe aprobar. <i>"No necesitas hacer nada más."</i></td></tr>
</table></div>
<p>El conteo de producto viene precargado con lo que debería quedar; ajusta con − y +. Una diferencia de más de 3 unidades abre un caso de inventario.</p>

<h3 id="op-ajustes">Ajustes</h3>
<ul>
<li><b>Ubicación (GPS)</b>: pastilla <i>Funciona / Con problema / Sin probar</i>, causa y solución si falla, último fix y botón <span class="ui">📡 Probar GPS</span>.</li>
<li><b>Por enviar</b>: cuántos registros faltan y <span class="ui">🔄 Reintentar enviar</span>.</li>
<li>🔊 Leer instrucciones en voz alta · 🔠 Texto más grande.</li>
<li>🚪 <b>Cerrar sesión</b>: si hay algo sin enviar, la app te avisa (<i>"Hay N registros sin enviar. Si sales ahora se perderán."</i>). Mejor espera a tener señal.</li>
</ul>

<h3 id="op-gps">Si el GPS no funciona</h3>
<div class="tbl"><table><tr><th>Mensaje</th><th>Causa</th><th>Solución</th></tr>
<tr><td>La app no está en modo seguro (https)</td><td>Abriste la app por una dirección <code>http://</code> o el certificado no está instalado.</td><td>Pide al supervisor la dirección <b>https://</b> y el certificado; vuelve a instalar la app desde ahí.</td></tr>
<tr><td>Ubicación bloqueada para esta app</td><td>Le dijiste "Bloquear" al permiso.</td><td>Ajustes del teléfono → Apps → Chrome (o Safari) → Permisos → Ubicación → Permitir.</td></tr>
<tr><td>El teléfono no entrega ubicación</td><td>Ubicación apagada.</td><td>Enciéndela en los ajustes rápidos.</td></tr>
<tr><td>Sin señal GPS por ahora</td><td>Estás bajo techo.</td><td>Sal a cielo abierto; la app reintenta sola y usa la última posición reciente.</td></tr>
</table></div>

<h3 id="op-offline">Sin señal: cómo funciona</h3>
""" + fig(states({"a": (120, 60, "Acción en la app", NAVY), "b": (400, 60, "Guardado cifrado", GRAY), "c": (680, 60, "Enviado ✓", GREEN), "d": (400, 190, "Requiere ayuda", RED)}, [("a", "b", "se guarda siempre"), ("b", "c", "con señal · cada 30 s"), ("b", "d", "rechazado"), ("d", "b", "Reintentar enviar")], h=240), "Cada venta, apertura, cierre o ayuda se guarda primero en el teléfono y se envía en orden. Un turno abierto sin señal se llama 'pendiente de enviar' hasta que el servidor lo confirma.") + """
<div class="callout warn">Nunca desinstales la app ni cierres sesión con registros pendientes: se perderían. Si cambias de teléfono, avisa al supervisor.</div>
"""

OP_STEPS = """
<h3 id="op-ej1">Ejemplo 1 · Un día normal (Operador Uno, Metro Insurgentes, carrito C-001)</h3>
<ol class="steps">
<li><b>Entrar</b> Usuario <code>op1</code>, contraseña, <span class="ui p">ENTRAR</span>.<div class="ex">Pantalla verde: "Bienvenido · 📍 Metro Insurgentes · Carrito C-001". A los 2 segundos pasas a Inicio con "Puesto cerrado · Turno 8:00 a.m. – 6:00 p.m.".</div></li>
<li><b>Abrir</b> <span class="ui g">ABRIR PUESTO</span>. Contesta los 5 puntos; la barra de progreso llega a 5/5 "Listo".<div class="ex">Todo en Sí → <span class="ui g">LISTO</span> → "LISTO PARA VENDER" → <span class="ui">VENDER</span>.</div></li>
<li><b>Primera venta en efectivo</b> Con "💵 Efectivo" seleccionado toca <b>100 g · $45</b>.<div class="ex">Toast "✓ Venta registrada · 100 g · $45". Contador: 1 venta · $45. La barra sigue en "✓ Guardado".</div></li>
<li><b>Venta con QR</b> Toca <span class="ui b">📱 QR / Tarjeta</span>, luego <b>75 g · $35</b>.<div class="ex">El botón se ve azul y el toast también. Después de la venta la forma de pago regresa a Efectivo.</div></li>
<li><b>Te equivocaste</b> Vendiste 50 g pero era 100 g. En el toast toca <span class="ui">↩ Deshacer</span> antes de 60 s.<div class="ex">Si ya decía "Última venta" y se había enviado, elige el motivo "🔁 Cambio de tamaño". Luego registra la venta correcta.</div></li>
<li><b>Merma</b> Se cayó una bolsa de 50 g. <span class="ui">🗑️ MERMA</span> → 50 → 1 → "💧 Derrame".<div class="ex">"Merma registrada" → <span class="ui">Volver a vender</span>. No cuenta como venta ni suma al efectivo esperado.</div></li>
<li><b>Cerrar</b> A las 6 p.m.: <span class="ui a">CERRAR PUESTO</span>.<div class="ex">"Debes tener $45" (sólo el efectivo; los $35 del QR no cuentan). Escribes 45 → CONTINUAR → producto: 50 g queda 37 (40 − 1 venta deshecha − 1 merma − … la app ya lo precarga) → CONTINUAR → checklist de salida todo Sí → CERRAR PUESTO → "✅ Cierre conciliado" → Terminar. Inicio muestra "Turno de hoy terminado".</div></li>
</ol>

<h3 id="op-ej2">Ejemplo 2 · Sin señal toda la mañana</h3>
<ol class="steps">
<li><b>Abrir sin internet</b> La barra dice "📴 Sin señal". Contestas el checklist y tocas LISTO.<div class="ex">Resultado "LISTO PARA VENDER · Se enviará cuando haya señal". En Inicio: "Abierto, pendiente de enviar". La barra se pone ámbar: "Pendiente de enviar (1)".</div></li>
<li><b>Vender igual</b> Cada venta suma al contador y a la lista pendiente.<div class="ex">"Pendiente de enviar (7)" con el puntito ámbar latiendo. Tu efectivo esperado se calcula en el teléfono.</div></li>
<li><b>Vuelve la red</b> No tienes que hacer nada.<div class="ex">En menos de 30 segundos la barra pasa a "✓ Guardado". Si algo quedó en rojo "Requiere ayuda", ve a Ajustes → Reintentar enviar.</div></li>
<li><b>Cerrar sin señal</b> También se puede.<div class="ex">"Debes tener $X (calculado en el teléfono)". El resultado que ves es provisional; el definitivo lo fija el servidor al sincronizar, y si hubo diferencia el supervisor lo verá en su lista.</div></li>
</ol>

<h3 id="op-ej3">Ejemplo 3 · Abriste con un pendiente y pediste ayuda</h3>
<ol class="steps">
<li><b>La terminal no enciende</b> En el checklist marcas "Terminal POS funciona: ✕ No" y LISTO.<div class="ex">"ABIERTO CON PENDIENTES · Ya avisamos al supervisor" con la tarjeta "Terminal POS no funciona: cobra sólo en efectivo y pide ayuda". Tocas CONTINUAR y puedes vender (en efectivo).</div></li>
<li><b>Pide ayuda</b> Inicio → <span class="ui b">NECESITO AYUDA</span> → <b>💳 Cobro</b>.<div class="ex">"📨 Enviado, te contactan". El supervisor lo ve como caso REVISAR "Problema de cobro" con tu ubicación.</div></li>
<li><b>Situación de riesgo</b> <span class="ui b">NECESITO AYUDA</span> → <b>🚨 Seguridad</b>.<div class="ex">Se envía sin esperar el GPS más de 3 s. "Mantente a salvo. Ayuda prioritaria en camino." Es un caso URGENTE para toda la red.</div></li>
</ol>

<h3 id="op-ej4">Ejemplo 4 · Cerraste por error y el administrador te reabre el turno</h3>
<ol class="steps">
<li><b>Avisa</b> Llama al supervisor/administrador: sólo el administrador puede "Continuar turno" y sólo el mismo día.</li>
<li><b>Vuelve a la app</b> Al abrirla (o en menos de un minuto si ya estaba abierta) Inicio cambia de "Turno de hoy terminado" a "Puesto abierto".<div class="ex">El contador muestra las ventas de antes ("$70 · 2 ventas") y puedes seguir vendiendo.</div></li>
<li><b>Cierra otra vez al final</b> "Debes tener" incluye todo el efectivo del día (antes y después de la reapertura).</li>
</ol>
"""

# =====================================================================
# SUPERVISOR
# =====================================================================
SUP_INTRO = """
<p>Coordinas los puntos de tu <b>zona</b> desde el backoffice (en el teléfono o en la computadora). El sistema ordena tu día: las reglas detectan problemas y te los presentan como <b>casos</b> por prioridad. Puedes:</p>
<div class="cards">
<div class="card"><h5>⚡ Mi día</h5><p>Casos URGENTE / REVISAR / NORMAL de tu zona y estado de cada punto.</p></div>
<div class="card"><h5>➜ Ruta de hoy</h5><p>Paradas sugeridas ordenadas por prioridad y cercanía, con navegación.</p></div>
<div class="card"><h5>🔍 Auditoría en sitio</h5><p>Checklist de 7 puntos, arqueo sorpresa, notas (dictado), hasta 3 fotos y acciones correctivas.</p></div>
<div class="card"><h5>⚑ Excepciones y casos</h5><p>Atender, cambiar estado/severidad/categoría, asignarte casos, agregar acciones, resolver con nota.</p></div>
<div class="card"><h5>$ Ventas · ▤ Inventario · ☺ Personas</h5><p>Reporte diario por turno, stock por punto y asistencia de tu zona.</p></div>
</div>
<div class="callout">Sólo ves tu zona. No ves Control Tower, Briefing, Activos, Reglas, Aprobaciones, Audit log ni Administración. No puedes editar precios ni parámetros ni reabrir turnos.</div>
""" + fig(flow([("Reglas del sistema", "cada 5 min", NAVY), ("Casos", "urgente · revisar · normal", ORANGE), ("Mi día / Ruta", "qué atender y en qué orden", BLUE), ("Atender", "estado, acciones, nota", GREEN), ("Auditoría", "checklist + arqueo + fotos", AMBER)]), "El flujo del supervisor: el sistema detecta, tú decides y dejas registro.")

SUP_QUICK = """
<div class="cards">
<div class="card"><h5><span class="n">1</span>Empieza en Mi día</h5><p>Entra (<code>sup1</code> en demo). Atiende primero el bloque <b>URGENTE · Atender ahora</b>; <b>REVISAR</b> va en la ruta; <b>NORMAL</b> sólo por muestreo.</p></div>
<div class="card"><h5><span class="n">2</span>Atiende un caso</h5><p><span class="ui b">Atender</span> → cambia Estado a <i>En proceso</i>, <span class="ui">Asignármelo</span>, agrega una acción correctiva y al terminar <span class="ui g">Resolver con nota</span>.</p></div>
<div class="card"><h5><span class="n">3</span>Planea la visita</h5><p><span class="ui">Ver ruta</span>: paradas numeradas, km entre ellas y <span class="ui">Navegar</span> (Google Maps).</p></div>
<div class="card"><h5><span class="n">4</span>Audita en el punto</h5><p><span class="ui">Auditar en sitio</span>: 7 preguntas Sí/No, efectivo contado, notas, fotos, acciones → <span class="ui p">Enviar auditoría</span>.</p></div>
<div class="card"><h5><span class="n">5</span>Cierra el día</h5><p>Ventas: ¿qué cierres tuvieron diferencia? Personas: ¿quién llegó tarde o faltó? Inventario: ¿qué punto está en rojo?</p></div>
</div>
<h3 id="sup-sev">Severidades y prioridad</h3>
<div class="tbl"><table><tr><th>Severidad</th><th>Significa</th><th>Ejemplos</th><th>Qué se espera de ti</th></tr>
<tr><td><span class="badge b-red">URGENTE</span></td><td>Riesgo o pérdida en curso</td><td>Punto sin abrir (20 min de gracia), fuera de geocerca 10 min, seguridad, batería &lt; 10 %, carrito no asegurado, diferencia de caja &gt; $100</td><td>Actuar ahora (llamar, ir, escalar)</td></tr>
<tr><td><span class="badge b-amber">REVISAR</span></td><td>Desviación que requiere visita</td><td>Ventas bajo trayectoria, merma &gt; 4 %, batería &lt; 25 %, sin sincronizar 30 min, cancelaciones anómalas, stock crítico, diferencia de caja &gt; $20</td><td>Incluirlo en la ruta de hoy</td></tr>
<tr><td><span class="badge b-green">NORMAL</span></td><td>Dentro de parámetros</td><td>Ayuda "Otro", puntos sin casos</td><td>Muestreo</td></tr>
</table></div>
""" + fig(bars("Cómo se calcula la prioridad de un caso (puntos)", [("Severidad URGENTE", 100, 170, RED), ("Severidad REVISAR", 50, 170, AMBER), ("Severidad NORMAL", 10, 170, GREEN), ("+ impacto (0–50)", 50, 170, BLUE), ("+ antigüedad (máx. 20)", 20, 170, GRAY)]), "prioridad = peso de severidad + impacto + minutos abierto ÷ 30 (tope 20). Un caso urgente reciente siempre va antes que uno de revisión antiguo.")

SUP_DETAIL = """
<h3 id="sup-midia">Mi día</h3>
<p>Tres bloques con contador: <b>URGENTE · Atender ahora</b> (vacío: <i>"Nada urgente. Bien."</i>), <b>REVISAR · Visita o ruta de hoy</b> y <b>NORMAL · Dentro de parámetros</b> (incluye los puntos sin casos). Cada tarjeta de caso muestra título, 📍 punto, ⏱ antigüedad, categoría, responsable y el botón <span class="ui b">Atender</span>. Las tarjetas de punto muestran estado, operador, ventas vs meta y los accesos <span class="ui">Auditar (muestreo)</span> y <span class="ui">Casos</span>. Se refresca cada 60 s.</p>
<p>Los casos <b>transitorios</b> (punto sin abrir, sin sincronizar, fuera de geocerca, batería baja) se resuelven solos si la condición desaparece y nadie los tomó: verás la resolución <i>"Resuelto automáticamente: la condición dejó de cumplirse"</i>.</p>

<h3 id="sup-ruta">Ruta de hoy</h3>
<p>Mapa numerado y lista de paradas: sólo puntos con casos abiertos, agrupados urgente → revisar → normal y, dentro de cada grupo, por vecino más cercano. Cada parada indica el motivo (hasta 3 títulos), prioridad, número de casos y km desde la anterior. Botones <span class="ui">Auditar en sitio</span>, <span class="ui">Ver casos</span> y <span class="ui">Navegar</span>.</p>

<h3 id="sup-audit">Auditoría en sitio</h3>
<div class="tbl"><table><tr><th>Bloque</th><th>Qué capturas</th><th>Efecto</th></tr>
<tr><td>Checklist Sí/No</td><td>Limpieza del punto y carrito · Uniforme completo · Producto en buen estado · Exhibición correcta · Precios visibles · Carrito seguro · POS/terminal funcionando</td><td>Cada No es una <b>no conformidad</b>; si hay alguna se abre un caso REVISAR "No conformidades en auditoría: …" (impacto 5 × fallos).</td></tr>
<tr><td>Arqueo sorpresa</td><td>Efectivo contado (MXN)</td><td>Se compara con el esperado del turno abierto; diferencia mayor al umbral ($20) abre caso "Arqueo sorpresa con diferencia de $X" (URGENTE si &gt; $100).</td></tr>
<tr><td>Notas</td><td>Texto o <span class="ui">🎤 Dictar</span></td><td>Quedan en la auditoría y en el caso.</td></tr>
<tr><td>Fotos (máx. 3)</td><td><span class="ui">📷 Agregar foto</span>; se reducen en el navegador</td><td>Evidencias visibles en el caso y en el detalle de la auditoría.</td></tr>
<tr><td>Acciones correctivas</td><td>Descripción, responsable (tú por defecto), fecha objetivo</td><td>Se crean en el caso; el responsable las marca "hecha".</td></tr>
</table></div>
<p>Si falta alguna respuesta: <i>"Faltan N respuesta(s) del checklist"</i>. Al enviar: <i>"Auditoría enviada. Se abrió N caso(s)."</i> (te lleva al primero) o <i>"Auditoría enviada sin no conformidades."</i></p>

<h3 id="sup-caso">Detalle de un caso</h3>
<p><b>Detalle</b> (descripción, categoría, origen, impacto, responsable, turno; si el sistema sugiere otra categoría verás <i>"Sugerencia IA: reclasificar como … (confianza N %)"</i> con <span class="ui">Aceptar sugerencia</span>; la decisión siempre es tuya). <b>Evidencias</b> (fotos del operador y de la auditoría). <b>Gestión</b>: Estado (Abierto / En proceso / Resuelto / Cerrado), Severidad, Categoría, <span class="ui">Asignármelo</span>, campo "Resolución / nota" y <span class="ui g">Resolver con nota</span>. <b>Acciones correctivas</b> con <span class="ui">Marcar hecha</span> / <span class="ui">Reabrir</span>. <b>Línea de tiempo</b> con todo lo ocurrido.</p>

<h3 id="sup-ventas">Ventas · Inventario · Personas</h3>
<ul>
<li><b>Ventas</b> (reporte diario): KPIs de ventas, transacciones, ticket, diferencia de caja, merma y precio vencido; gráfica por punto; tabla por turno con efectivo esperado vs contado y estado del cierre.</li>
<li><b>Inventario</b>: balance por punto y presentación. Rojo = por debajo del mínimo (10 u), ámbar = menos del doble (20 u). No puedes bloquear lotes (eso es de Operaciones).</li>
<li><b>Personas</b>: check-in/out por asignación, retraso (rojo &gt; 20 min), estados Presente / Tarde / Ausente / Pendiente / Terminó.</li>
</ul>
""" + fig(semaforo("Semáforos que verás en Ventas e Inventario", [("Ticket promedio", [("< $36", RED), ("$36 – $38.99", AMBER), ("≥ $39", GREEN)]), ("Transacciones por turno", [("< 45", RED), ("45 – 59", AMBER), ("≥ 60", GREEN)]), ("Merma (% de unidades)", [("≤ 2 %", GREEN), ("2 – 4 %", AMBER), ("> 4 %", RED)]), ("Stock por presentación", [("< 10 u", RED), ("10 – 19 u", AMBER), ("≥ 20 u", GREEN)])]), "Umbrales del PRD §15. El administrador puede ajustar los de caja e inventario en Parámetros.")

SUP_STEPS = """
<h3 id="sup-ej1">Ejemplo 1 · Mañana con un punto sin abrir</h3>
<ol class="steps">
<li><b>8:25 a.m. — Mi día</b> En URGENTE aparece "Punto sin abrir: Parque México · ⏱ 5 min · El operador Operador Dos no ha abierto; 25 min después de la hora planeada".<div class="ex">La regla <code>no_open</code> corre cada 5 minutos con 20 min de gracia.</div></li>
<li><b>Atender</b> <span class="ui b">Atender</span> → Estado <i>En proceso</i> → <span class="ui">Asignármelo</span>. Llamas al operador.<div class="ex">Agrega la acción "Confirmar llegada del operador · hoy". Nota: "Operador en camino, llega 8:45".</div></li>
<li><b>Se resuelve solo</b> A las 8:47 el operador abre.<div class="ex">Como el caso ya tiene responsable (tú), no se autocierra: tú lo resuelves con <span class="ui g">Resolver con nota</span> "Abrió 8:47, retraso por transporte". El retraso queda en Personas como "Tarde · 47 min".</div></li>
</ol>

<h3 id="sup-ej2">Ejemplo 2 · Auditoría con no conformidad y arqueo</h3>
<ol class="steps">
<li><b>Ruta</b> <span class="ui">Ver ruta</span>: parada 1 Alameda Central (REVISAR: "Merma alta"), parada 2 Metro Insurgentes. <span class="ui">Navegar</span>.</li>
<li><b>En el punto</b> <span class="ui">Auditar en sitio</span>. Checklist: todo Sí menos "Precios visibles: No".<div class="ex">El badge cambia a "1 no conformidad".</div></li>
<li><b>Arqueo</b> Cuentas $312. El turno lleva $290 esperados.<div class="ex">Diferencia +$22 &gt; $20 → se abrirá "Arqueo sorpresa con diferencia de $22" (REVISAR).</div></li>
<li><b>Nota y foto</b> <span class="ui">🎤 Dictar</span>: "Letrero de precios caído, se indicó al operador colocarlo". <span class="ui">📷 Agregar foto</span> del exhibidor.</li>
<li><b>Acción correctiva</b> "Colocar letrero de precios" · responsable: Operador Tres · fecha: hoy → <span class="ui">+ Agregar</span>.</li>
<li><b>Enviar</b> <span class="ui p">Enviar auditoría</span>.<div class="ex">"Auditoría enviada. Se abrió 2 caso(s)." Te lleva al caso "No conformidades en auditoría: precios visibles", con tu foto en Evidencias y la acción pendiente. Desde ahí, <span class="ui">Ver auditoría</span> muestra el detalle completo.</div></li>
</ol>

<h3 id="sup-ej3">Ejemplo 3 · Cierre con diferencia de caja</h3>
<ol class="steps">
<li><b>6:10 p.m.</b> Aparece en REVISAR "Diferencia de caja de $45.00 · Esperado $1,020.00, contado $975.00 (faltante)".</li>
<li><b>Verifica</b> En <b>Ventas</b> filtra la fecha: el turno de Metro Insurgentes muestra Efectivo esperado $1,020 · Contado $975 · Diferencia −$45 · Estado "Diferencia".</li>
<li><b>Concilia</b> Hablas con el operador; encontró $45 en el cajón del POS.<div class="ex">Resolver con nota: "Efectivo localizado en cajón POS, conciliado". Si hubiera sido &gt; $100 el caso sería URGENTE y Finanzas tendría una aprobación pendiente.</div></li>
</ol>
"""

# =====================================================================
# OPERACIONES
# =====================================================================
OPS_INTRO = """
<p>Diriges la red completa desde el <b>Control Tower</b>. Ves todos los puntos y zonas, ajustas las reglas que generan casos, gestionas inventario, activos y mantenimiento, y lees el audit log. Puedes:</p>
<div class="cards">
<div class="card"><h5>◎ Control Tower</h5><p>KPIs con semáforo, mapa, alertas y tabla de puntos en tiempo real. <span class="ui">Ejecutar reglas ahora</span>.</p></div>
<div class="card"><h5>☰ Briefing</h5><p>Headline del día, decisiones pendientes con recomendación y números para dirección.</p></div>
<div class="card"><h5>⚑ Excepciones · Supervisor · Ruta</h5><p>Todo lo que ve un supervisor, pero de toda la red, y con asignación a cualquier persona.</p></div>
<div class="card"><h5>$ Ventas · ▤ Inventario · ☺ Personas</h5><p>Reporte diario, stock y <b>bloqueo de lotes</b>, asistencia.</p></div>
<div class="card"><h5>⚙ Activos</h5><p>Carritos, baterías, cargadores y POS; preventivos vencidos y tickets correctivos.</p></div>
<div class="card"><h5>⚖ Reglas · ≡ Audit log</h5><p>Activar/desactivar reglas, umbrales y severidad; trazabilidad de todo cambio.</p></div>
</div>
<div class="callout">Límites: <b>no</b> decides aprobaciones (verás "Decide Finanzas"), en Administración sólo lees Precios y Parámetros, y no puedes reabrir turnos cerrados (administrador).</div>
""" + fig(flow([("Eventos", "ventas, GPS, cierres, ayuda", GRAY), ("Motor de reglas", "cada 5 min · 11 reglas", NAVY), ("Alerta + Caso", "dedupe regla:punto:día", ORANGE), ("Control Tower", "semáforos y prioridad", BLUE), ("Decisión humana", "supervisor / ops / finanzas", GREEN)]), "Del dato a la decisión: las reglas nunca actúan solas; producen casos que alguien atiende.")

OPS_QUICK = """
<div class="cards">
<div class="card"><h5><span class="n">1</span>Abre el Control Tower</h5><p>Entra con <code>ops</code>. Mira los 6 KPIs: rojo = actuar, ámbar = vigilar. El contador de excepciones te lleva a los casos por severidad.</p></div>
<div class="card"><h5><span class="n">2</span>Revisa la tabla de puntos</h5><p>Estado (Abierto / Tarde / Sin señal / Cerrado), geocerca, batería, ventas vs meta, caja, stock, casos. Acciones <span class="ui">Casos</span> y <span class="ui">Auditar</span>.</p></div>
<div class="card"><h5><span class="n">3</span>Lee el Briefing</h5><p>Top 8 decisiones con "por qué" y "Recomendación". Úsalo para la reunión de la mañana.</p></div>
<div class="card"><h5><span class="n">4</span>Ajusta reglas</h5><p>Reglas → switch Activa, parámetros (minutos, %, unidades), severidad → <span class="ui">Guardar</span>. Prueba con <span class="ui p">Ejecutar reglas ahora</span>.</p></div>
<div class="card"><h5><span class="n">5</span>Inventario y activos</h5><p>Bloquea un lote con motivo cuando haya reporte de calidad; crea tickets de mantenimiento cuando un preventivo esté VENCIDO.</p></div>
<div class="card"><h5><span class="n">6</span>Audita cambios</h5><p>Audit log: filtra por entidad, ID o acción (p. ej. <code>rule.update</code>, <code>shift.reopen</code>).</p></div>
</div>
""" + fig(semaforo("Semáforos del Control Tower", [("Ventas vs meta (avance)", [("< 75 %", RED), ("75 – 99 %", AMBER), ("≥ 100 %", GREEN)]), ("Transacciones por punto", [("< 45", RED), ("45 – 59", AMBER), ("≥ 60", GREEN)]), ("Ticket promedio", [("< $36", RED), ("$36 – $38.99", AMBER), ("≥ $39", GREEN)]), ("Batería del teléfono", [("< 10 %", RED), ("10 – 24 %", AMBER), ("≥ 25 %", GREEN)]), ("Merma", [("≤ 2 %", GREEN), ("2 – 4 %", AMBER), ("> 4 %", RED)])]), "Umbrales fijos del PRD §15. La meta por punto es $2,340 / 60 tx salvo que el punto tenga una propia.")

OPS_DETAIL = """
<h3 id="ops-ct">Control Tower</h3>
<p>Selector de fecha, <span class="ui">Actualizar</span>, <span class="ui">Briefing</span>, <span class="ui p">Ejecutar reglas ahora</span> (toast <i>"Reglas ejecutadas: N alertas, N casos nuevos"</i>). Se refresca solo cada 60 s.</p>
<div class="tbl"><table><tr><th>KPI</th><th>Cálculo</th></tr>
<tr><td>Puntos</td><td>Programados hoy, con desglose abiertos / tarde / cerrados / sin señal.</td></tr>
<tr><td>Ventas hoy</td><td>Suma de ventas registradas vs suma de metas; barra de avance.</td></tr>
<tr><td>Transacciones</td><td>Total y promedio por punto (meta 60).</td></tr>
<tr><td>Ticket promedio</td><td>Ventas ÷ transacciones.</td></tr>
<tr><td>Forecast cierre</td><td>Ritmo actual extrapolado a 10 h, tope 1.5× la meta.</td></tr>
<tr><td>Excepciones abiertas</td><td>Contadores URGENTE / REVISAR / NORMAL (enlazan a Excepciones filtradas).</td></tr>
</table></div>
""" + fig(states({"ns": (110, 130, "No programado", GRAY), "cl": (380, 130, "Cerrado", BLUE), "la": (380, 240, "Tarde", AMBER), "op": (680, 130, "Abierto", GREEN), "of": (860, 240, "Sin señal", GRAY)}, [("ns", "cl", "asignación de hoy"), ("cl", "la", "+20 min sin abrir"), ("cl", "op", "abre"), ("la", "op", "abre tarde"), ("op", "of", "30 min sin actividad"), ("of", "op", "sincroniza"), ("op", "cl", "cierra / transfiere")], h=290), "Estados de un punto en la tabla del Control Tower. 'Sin señal' es un turno abierto sin actividad en 30 min (regla sync_stale).") + """
<p>Columnas de la tabla: Punto · Estado · Operador · Apertura · Último GPS (hora + <span class="badge b-green">En geocerca</span> / <span class="badge b-red">Fuera</span>) · Batería · Ventas / meta · Tx · Ticket · Caja (<span class="badge b-amber">Pendiente</span> mientras está abierto, <span class="badge b-green">OK</span> conciliado, <span class="badge b-red">Diferencia</span>) · Stock (OK / Bajo / Crítico) · Casos (N URG / N REV) · acciones.</p>

<h3 id="ops-brief">Briefing</h3>
<p>Headline: <i>"2 de 3 puntos abiertos, ventas $1,550 (22 % de la meta), 4 urgentes y 6 por revisar."</i> Luego <b>Decisiones</b> (top 8 por prioridad) con severidad, por qué y una recomendación fija por tipo de caso, y <b>Números</b> del día.</p>
<div class="tbl"><table><tr><th>Caso</th><th>Recomendación que muestra</th></tr>
<tr><td>Punto sin abrir</td><td>Llamar al operador; si no responde en 15 min, enviar flotante o supervisor</td></tr>
<tr><td>Fuera de geocerca</td><td>Contactar al operador y verificar ubicación; considerar visita</td></tr>
<tr><td>Ventas bajo trayectoria</td><td>Revisar afluencia y producto; evaluar reubicación temporal</td></tr>
<tr><td>Merma alta</td><td>Revisar manejo de producto y calidad del lote; auditar en la próxima visita</td></tr>
<tr><td>Diferencia de caja</td><td>Conciliar con el operador; si es grave, escalar a Finanzas y bloquear pagos pendientes</td></tr>
<tr><td>Batería baja</td><td>Enviar batería de reemplazo o indicar carga inmediata</td></tr>
<tr><td>Sin sincronizar</td><td>Verificar conectividad del dispositivo; llamar al operador</td></tr>
<tr><td>Stock crítico</td><td>Programar reposición hoy desde almacén</td></tr>
<tr><td>Seguridad</td><td>Aplicar protocolo de seguridad; contactar al operador de inmediato</td></tr>
</table></div>

<h3 id="ops-reglas">Reglas</h3>
<p>Cada regla evalúa cada 5 minutos (o al pulsar <span class="ui p">Ejecutar reglas ahora</span>) y, si dispara y no existe ya un caso abierto de esa regla para ese punto hoy, crea <b>alerta + caso</b>. Por fila: switch <b>Activa</b>, parámetros editables, severidad y <span class="ui">Guardar</span>. Cambios al audit log.</p>
<div class="tbl"><table><tr><th>Regla</th><th>Severidad</th><th>Parámetros (default)</th><th>Dispara cuando</th></tr>
<tr><td>Punto sin abrir</td><td><span class="badge b-red">URGENTE</span></td><td>grace_minutes 20</td><td>Asignación de hoy sin turno pasados 20 min de la hora planeada</td></tr>
<tr><td>Fuera de geocerca</td><td><span class="badge b-red">URGENTE</span></td><td>minutes 10</td><td>Último GPS fuera del radio (150 m) por ≥ 10 min</td></tr>
<tr><td>Ventas bajo trayectoria</td><td><span class="badge b-amber">REVISAR</span></td><td>pct 60 · min_hours 2</td><td>Con ≥ 2 h abierto, ventas &lt; 60 % de la meta prorrateada</td></tr>
<tr><td>Merma alta</td><td><span class="badge b-amber">REVISAR</span></td><td>pct 4</td><td>merma / (ventas + merma) &gt; 4 %</td></tr>
<tr><td>Diferencia de caja</td><td>REVISAR / URGENTE</td><td>hereda Parámetros ($20 / $100)</td><td>|contado − esperado| &gt; umbral al cerrar; grave → urgente + aprobación</td></tr>
<tr><td>Inventario inconsistente</td><td><span class="badge b-amber">REVISAR</span></td><td>hereda (3 u)</td><td>|conteo − teórico| &gt; 3 unidades</td></tr>
<tr><td>Batería baja</td><td>REVISAR / URGENTE</td><td>warn 25 · critical 10</td><td>Último ping &lt; 25 %; &lt; 10 % urgente</td></tr>
<tr><td>Cancelaciones anómalas</td><td><span class="badge b-amber">REVISAR</span></td><td>count 3 · pct 10</td><td>&gt; 3 cancelaciones o &gt; 10 % de las ventas del turno</td></tr>
<tr><td>Sin sincronizar</td><td><span class="badge b-amber">REVISAR</span></td><td>minutes 30</td><td>Turno abierto sin evento ni ping en 30 min</td></tr>
<tr><td>Mantenimiento vencido</td><td><span class="badge b-amber">REVISAR</span></td><td>—</td><td>Activo con preventivo vencido (dedupe por activo)</td></tr>
<tr><td>Stock crítico</td><td><span class="badge b-amber">REVISAR</span></td><td>min_units 10</td><td>Punto abierto con alguna presentación &lt; 10 u</td></tr>
</table></div>
<p>Las reglas de caja e inventario muestran <span class="badge b-gray">heredado de Parámetros</span>; puedes <span class="ui">Definir override</span> sólo para esa regla o <span class="ui">Quitar override</span> para volver a heredar. Las reglas transitorias (sin abrir, sin sincronizar, geocerca, batería) se autoresuelven cuando la condición desaparece si nadie tomó el caso.</p>

<h3 id="ops-inv">Inventario y lotes</h3>
<p>Balance por punto y presentación reconstruido desde movimientos (recepciones, ventas, merma, conteos, transferencias). Muestra <i>(teórico N)</i> cuando el conteo difiere. <b>Lotes</b>: <span class="ui r">Bloquear</span> abre un modal con motivo obligatorio; retira del balance de cada punto las unidades recibidas de ese lote y evita nuevas entregas. Toast <i>"Lote L-2026-001 bloqueado. 3 punto(s) afectado(s)."</i></p>

<h3 id="ops-activos">Activos y mantenimiento</h3>
<p>Tabla de activos (batería cada 30 d, cargador 90 d, POS 180 d en el seed) con <span class="badge b-red">VENCIDO</span> cuando pasa el próximo preventivo, y <span class="ui">+ Ticket</span>. Tickets con Título, Descripción, Severidad, Tipo (Correctivo / Preventivo) y ciclo <span class="ui">Iniciar</span> → <span class="ui">Resolver</span> (con texto de resolución) → <span class="ui">Cerrar</span>.</p>

<h3 id="ops-audit">Audit log</h3>
<p>Filtros: Entidad (case, action, audit, rule, approval, lot, device, users, points, carts, assignments, presentations, price_version, zones, maintenance_ticket, token), ID de entidad, "Acción contiene", límite. Cada fila: cuándo, actor (o "sistema"), acción, entidad, diff <i>campo: antes → después</i>, motivo, IP/dispositivo.</p>

<h3 id="ops-admin">Administración (sólo lectura)</h3>
<p>Ves <b>Precios</b> (versiones, precio por presentación, ventas con cada versión) y <b>Parámetros</b> con el aviso <i>"Sólo lectura para tu rol; edita un administrador."</i> Úsalo para verificar umbrales vigentes antes de interpretar un caso.</p>
"""

OPS_STEPS = """
<h3 id="ops-ej1">Ejemplo 1 · Arranque del día (8:30 a.m.)</h3>
<ol class="steps">
<li><b>Control Tower</b> KPI Puntos: 3 programados · 2 abiertos · 1 tarde. Excepciones: 1 URGENTE.<div class="ex">Tabla: Parque México en <span class="badge b-amber">Tarde</span>, Operador Dos, sin GPS; casos "1 URG".</div></li>
<li><b>Briefing</b> Decisión 1: "Punto sin abrir: Parque México · Recomendación: Llamar al operador; si no responde en 15 min, enviar flotante o supervisor".</li>
<li><b>Actúa</b> <span class="ui">Abrir caso →</span> → Estado <i>En proceso</i> → Asignar a: Supervisor Centro → acción "Llamar al operador · Supervisor Centro · hoy".<div class="ex">El supervisor lo ve en su Mi día como URGENTE asignado a él.</div></li>
<li><b>Verifica a las 9:00</b> <span class="ui">Actualizar</span>: Parque México ahora <span class="badge b-green">Abierto</span>, "En geocerca", batería 88 %. El caso pasa a resuelto por el supervisor con nota.</li>
</ol>

<h3 id="ops-ej2">Ejemplo 2 · Ajustar una regla que hace ruido</h3>
<ol class="steps">
<li><b>Síntoma</b> Cada mañana hay 3 casos "Sin sincronizar" a los 30 min de abrir, porque los operadores venden poco la primera media hora.</li>
<li><b>Reglas</b> Fila "Sin sincronizar": cambia <code>minutes</code> de 30 a 45 → <span class="ui">Guardar</span>.<div class="ex">Toast "Regla sync_stale guardada". En Audit log aparece <code>rule.update</code> con "minutes: 30 → 45" y tu usuario.</div></li>
<li><b>Prueba</b> <span class="ui p">Ejecutar reglas ahora</span>.<div class="ex">"Motor ejecutado: 0 alertas, 0 casos". Los casos anteriores sin responsable se autoresolvieron.</div></li>
</ol>

<h3 id="ops-ej3">Ejemplo 3 · Reporte de calidad de un lote</h3>
<ol class="steps">
<li><b>Aviso</b> El proveedor reporta humedad en el lote L-2026-001.</li>
<li><b>Inventario → Lotes</b> <span class="ui r">Bloquear</span> → motivo "Reporte de calidad del proveedor: humedad" → <span class="ui r">Bloquear lote</span>.<div class="ex">"Lote L-2026-001 bloqueado. 3 punto(s) afectado(s)." y la lista: Metro Insurgentes · 50 g · 40 u retiradas del balance, …</div></li>
<li><b>Consecuencia</b> Los puntos afectados pasan a stock Crítico; la regla "Stock crítico" abre casos REVISAR y el Briefing recomienda "Programar reposición hoy desde almacén".</li>
</ol>

<h3 id="ops-ej4">Ejemplo 4 · Preventivo vencido</h3>
<ol class="steps">
<li><b>Activos</b> C-002-BATTERY muestra Próximo preventivo <span class="badge b-red">VENCIDO</span>; ya existe el caso "Mantenimiento vencido: C-002-BATTERY".</li>
<li><b>+ Ticket</b> Título "Preventivo batería C-002", Tipo Preventivo, Severidad REVISAR → <span class="ui p">Crear ticket</span>.</li>
<li><b>Ciclo</b> <span class="ui">Iniciar</span> cuando lo toma mantenimiento → <span class="ui">Resolver</span> con "Cambio de celdas y prueba de carga" → <span class="ui">Cerrar</span>.<div class="ex">Al resolver se actualiza el último preventivo y el caso deja de disparar.</div></li>
</ol>
"""

# =====================================================================
# FINANZAS
# =====================================================================
FIN_INTRO = """
<p>Custodias el dinero y la trazabilidad. Ves toda la red en modo lectura y tienes una decisión exclusiva: <b>aprobar o rechazar</b> lo que requiere autorización humana (diferencias de caja graves, pagos, compras, ajustes). Puedes:</p>
<div class="cards">
<div class="card"><h5>✓ Aprobaciones</h5><p>Decidir cada solicitud pendiente con nota. Quien solicita nunca aprueba.</p></div>
<div class="card"><h5>$ Ventas</h5><p>Reporte diario por turno: efectivo esperado vs contado, diferencia, digital, merma, precio vencido.</p></div>
<div class="card"><h5>◎ Control Tower · ☰ Briefing</h5><p>Estado de la red y decisiones del día (sin ejecutar reglas).</p></div>
<div class="card"><h5>⚑ Excepciones</h5><p>Leer casos y su línea de tiempo completa, incluido el audit log.</p></div>
<div class="card"><h5>≡ Audit log · Administración</h5><p>Trazabilidad de todo cambio; Precios y Parámetros en lectura.</p></div>
</div>
<div class="callout">No puedes editar casos, reglas, precios ni parámetros, ni ver Supervisor, Ruta, Inventario, Personas o Activos.</div>
""" + fig(flow([("Cierre con diferencia", "|contado − esperado| > $100", RED), ("Caso URGENTE", "para el supervisor", ORANGE), ("Aprobación pendiente", "tipo cash_difference", AMBER), ("Finanzas decide", "Aprobar / Rechazar + nota", BLUE), ("Audit log", "quién, cuándo, por qué", GREEN)]), "Ruta de una diferencia de caja grave hasta tu decisión. Con diferencias entre $20 y $100 sólo hay caso, sin aprobación.")

FIN_QUICK = """
<div class="cards">
<div class="card"><h5><span class="n">1</span>Entra</h5><p>Usuario <code>finanzas</code>. Llegas al Control Tower; ve a <b>Aprobaciones</b>.</p></div>
<div class="card"><h5><span class="n">2</span>Revisa pendientes</h5><p>Filtro "Pendientes" (default). Cada fila: solicitada, tipo, título, monto, quién solicitó, nota.</p></div>
<div class="card"><h5><span class="n">3</span>Investiga</h5><p>Para una diferencia de caja: abre <b>Ventas</b> del día y el <b>caso</b> vinculado (línea de tiempo, evidencias, nota del supervisor).</p></div>
<div class="card"><h5><span class="n">4</span>Decide</h5><p><span class="ui g">Aprobar</span> o <span class="ui r">Rechazar</span> → nota (motivo o referencia) → <span class="ui p">Confirmar</span>.</p></div>
<div class="card"><h5><span class="n">5</span>Cierra el mes</h5><p>Ventas por fecha: totales, diferencias, digital vs efectivo, ventas con precio vencido. Audit log para justificar cambios.</p></div>
</div>
<h3 id="fin-tipos">Tipos de aprobación</h3>
<div class="tbl"><table><tr><th>Tipo</th><th>Origen</th><th>Qué revisar antes de decidir</th></tr>
<tr><td>Ajuste (diferencia de caja)</td><td>Automático al cerrar con |diferencia| &gt; $100 (parámetro <code>cash_difference_severe_cents</code>)</td><td>Caso del turno, nota de conciliación del supervisor, historial del operador, evidencias.</td></tr>
<tr><td>Pago</td><td>Solicitud manual</td><td>Referencia, monto, solicitante.</td></tr>
<tr><td>Compra</td><td>Solicitud manual</td><td>Presupuesto y necesidad (p. ej. reposición tras bloqueo de lote).</td></tr>
</table></div>
<p>Estados: <span class="badge b-amber">Pendiente</span> → <span class="badge b-green">Aprobada</span> / <span class="badge b-red">Rechazada</span>. Un cuarto estado, <span class="badge b-gray">Cancelada</span>, aparece cuando el administrador reabre el turno que originó la diferencia: la aprobación deja de tener sentido porque el turno volverá a cerrarse y a conciliarse.</p>
"""

FIN_DETAIL = """
<h3 id="fin-apr">Aprobaciones</h3>
<p>Subtítulo: <i>"Human-in-the-loop: pagos, compras y ajustes materiales requieren decisión humana. Quien solicita no puede aprobar."</i> Filtro Pendientes / Aprobadas / Rechazadas / Canceladas (turno reabierto) / Todas. Columnas: Solicitada · Tipo · Título · Monto · Solicitó · Nota · Estado · Decisión. En pendientes: <span class="ui g">Aprobar</span> y <span class="ui r">Rechazar</span>; el modal muestra el monto, un campo <b>Nota</b> y <span class="ui p">Confirmar</span>. Toast "Aprobada" / "Rechazada". Cada decisión queda en el audit log (<code>approval.decide</code>) con tu usuario, IP y nota.</p>

<h3 id="fin-ventas">Ventas (reporte diario)</h3>
<div class="tbl"><table><tr><th>KPI / columna</th><th>Significado</th></tr>
<tr><td>Ventas totales · Transacciones · Ticket promedio</td><td>Del día seleccionado, todos los puntos.</td></tr>
<tr><td>Diferencia de caja</td><td>Suma de (contado − esperado) de los cierres; verde si 0.</td></tr>
<tr><td>Merma</td><td>Unidades y % sobre unidades vendidas + merma (ámbar 2–4 %, rojo &gt; 4 %).</td></tr>
<tr><td>Ventas con precio vencido</td><td>Ventas hechas sin señal con una versión de precio ya desactivada; se aceptan 72 h de gracia y se marcan. Ámbar si &gt; 0.</td></tr>
<tr><td>Por turno</td><td>Punto, operador, apertura/cierre, ventas, tx, ticket, digital, efectivo esperado, contado, diferencia, cancelaciones, merma, precio vencido, estado (Conciliado / Diferencia / Abierto).</td></tr>
</table></div>
""" + fig(semaforo("Umbrales de caja (Parámetros del administrador)", [("Diferencia por cierre", [("≤ $20 conciliado", GREEN), ("$20 – $100 caso REVISAR", AMBER), ("> $100 URGENTE + aprobación", RED)])]), "cash_difference_threshold_cents = 2000 y cash_difference_severe_cents = 10000 por defecto; se ven en Administración → Parámetros.") + """
<h3 id="fin-ct">Control Tower y Briefing</h3>
<p>Los mismos KPIs, mapa, alertas y tabla que Operaciones, sin el botón "Ejecutar reglas ahora" y sin "Continuar turno". El Briefing incluye "Cierres con diferencia de caja" en la tarjeta Números.</p>

<h3 id="fin-casos">Excepciones y casos (lectura)</h3>
<p>Lista de casos con filtros y detalle completo: descripción, evidencias, acciones correctivas y línea de tiempo con las entradas del audit log (quién cambió qué y cuándo). No verás la tarjeta "Gestión".</p>

<h3 id="fin-audit">Audit log y Administración</h3>
<p>Audit log con filtros por entidad (approval, price_version, rule, shift…), ID y acción. En Administración sólo lees <b>Precios</b> (qué versión estuvo vigente y cuántas ventas usó cada una) y <b>Parámetros</b>.</p>
"""

FIN_STEPS = """
<h3 id="fin-ej1">Ejemplo 1 · Diferencia de caja grave</h3>
<ol class="steps">
<li><b>6:20 p.m.</b> Aprobaciones → Pendientes: "Diferencia de caja grave en turno 7a3f21c9 · Monto −$405.00 · Solicitó: Operador Uno".<div class="ex">Se creó automáticamente al cerrar con contado $0 y esperado $405.</div></li>
<li><b>Investiga</b> Ventas (hoy): Metro Insurgentes · Esperado $405 · Contado $0 · Estado Diferencia. Excepciones: caso URGENTE "Diferencia de caja de $405.00", línea de tiempo: el supervisor anotó "Operador olvidó contar; efectivo entregado en oficina 6:40 p.m., recibo #118".</li>
<li><b>Decide</b> <span class="ui g">Aprobar</span> → Nota "Efectivo recibido en oficina, recibo #118" → <span class="ui p">Confirmar</span>.<div class="ex">Toast "Aprobada". Audit log: approval.decide · status: pending → approved · tu usuario · la nota.</div></li>
</ol>

<h3 id="fin-ej2">Ejemplo 2 · La aprobación aparece como Cancelada</h3>
<ol class="steps">
<li><b>Contexto</b> El operador cerró por error a media jornada con diferencia grave; el administrador reabrió el turno ("Continuar turno").</li>
<li><b>Qué ves</b> En el filtro "Canceladas (turno reabierto)": la aprobación con nota "Superado: turno reabierto por administrador (…motivo…)".</li>
<li><b>Qué hacer</b> Nada: cuando el operador vuelva a cerrar, el sistema concilia contra todas las ventas del día y, si vuelve a haber diferencia grave, generará una aprobación nueva.</li>
</ol>

<h3 id="fin-ej3">Ejemplo 3 · Cierre semanal</h3>
<ol class="steps">
<li><b>Ventas por día</b> Cambia la fecha lunes a domingo y anota Ventas totales, Diferencia de caja y Ventas con precio vencido.<div class="ex">Miércoles: "Precio vencido: 4" → esa mañana el administrador desactivó la versión v1; las 4 ventas sin señal usaron el precio anterior dentro de las 72 h de gracia. Es esperado, no un error.</div></li>
<li><b>Aprobaciones</b> Filtro "Todas": confirma que no queda nada pendiente de más de 24 h.</li>
<li><b>Audit log</b> Entidad price_version: quién creó/desactivó versiones y cuándo, para justificar el cambio de precio en el reporte.</li>
</ol>
"""

# =====================================================================
# ADMINISTRADOR
# =====================================================================
ADM_INTRO = """
<p>Tienes todos los permisos. Además de todo lo que hacen Operaciones, Supervisor y Finanzas, configuras el sistema y tomas las decisiones que nadie más puede:</p>
<div class="cards">
<div class="card"><h5>⚒ Administración</h5><p>Usuarios (y restablecer contraseña), puntos, carritos, asignaciones, presentaciones, versiones de precio, dispositivos, zonas.</p></div>
<div class="card"><h5>🎚 Parámetros</h5><p>Umbrales de caja, ventana de cancelación, intervalo GPS, muestreo de fotos, retención, meta por defecto, ventana de reapertura, tolerancia de inventario.</p></div>
<div class="card"><h5>⚖ Reglas</h5><p>Activar, parametrizar y cambiar severidad de las 11 reglas.</p></div>
<div class="card"><h5>▶ Continuar turno</h5><p>Reabrir un turno cerrado hoy para que el operador siga vendiendo y vuelva a cerrar.</p></div>
<div class="card"><h5>✓ Aprobaciones</h5><p>Decidir junto con Finanzas.</p></div>
<div class="card"><h5>📱 Dispositivos</h5><p>Revocar un teléfono perdido: su sesión muere al instante.</p></div>
</div>
<div class="callout warn">Todo lo que haces queda en el audit log con tu usuario, IP y motivo. Las bajas son lógicas (nunca se borra historia). Los precios nunca se editan: se crean versiones.</div>
""" + fig(flow([("Configurar", "zonas → puntos → carritos → usuarios", NAVY), ("Catálogo", "presentaciones → versión de precio", ORANGE), ("Operar", "asignaciones diarias", BLUE), ("Ajustar", "parámetros y reglas", AMBER), ("Excepciones", "reabrir turno · revocar · restablecer", RED)]), "Orden recomendado de puesta en marcha y las tareas recurrentes del administrador.")

ADM_QUICK = """
<div class="cards">
<div class="card"><h5><span class="n">1</span>Alta de un operador</h5><p>Administración → Usuarios → <span class="ui p">+ Nuevo</span>: usuario, nombre, rol Operador, contraseña, zona → <span class="ui p">Crear</span>. Entra sólo por la PWA.</p></div>
<div class="card"><h5><span class="n">2</span>Asignación de hoy</h5><p>Asignaciones → + Nuevo: operador, punto, carrito, fecha. Sin horario usa el del punto.</p></div>
<div class="card"><h5><span class="n">3</span>Cambio de precio</h5><p>Precios → <span class="ui p">+ Nueva versión</span>: nombre y precio por presentación → vigente ahora. Luego desactiva la anterior.</p></div>
<div class="card"><h5><span class="n">4</span>Contraseña olvidada</h5><p>Usuarios → <span class="ui">Restablecer contraseña</span>: copia la temporal (se muestra una sola vez); el usuario deberá cambiarla al entrar.</p></div>
<div class="card"><h5><span class="n">5</span>Teléfono perdido</h5><p>Dispositivos → <span class="ui r">Revocar</span> con motivo. La app del operador muestra "Este teléfono fue dado de baja".</p></div>
<div class="card"><h5><span class="n">6</span>Cerró por error</h5><p>Control Tower (fecha de hoy) o Asignaciones → <span class="ui p">Continuar turno</span> → motivo → <span class="ui p">Reabrir turno</span>.</p></div>
</div>
<h3 id="adm-params">Parámetros (Administración → Parámetros)</h3>
<div class="tbl"><table><tr><th>Parámetro</th><th>Default</th><th>Efecto</th></tr>
<tr><td>cash_difference_threshold_cents</td><td>2000 ($20)</td><td>Diferencia de caja a partir de la cual se abre caso REVISAR (cierre y arqueo sorpresa).</td></tr>
<tr><td>cash_difference_severe_cents</td><td>10000 ($100)</td><td>Diferencia grave: caso URGENTE + aprobación de Finanzas.</td></tr>
<tr><td>cancel_window_minutes</td><td>5</td><td>Minutos en que el operador puede cancelar su propia venta ya enviada.</td></tr>
<tr><td>gps_interval_seconds</td><td>120</td><td>Cada cuánto envía GPS la PWA con turno abierto (mín. 10).</td></tr>
<tr><td>photo_sampling_pct</td><td>10</td><td>% de aperturas (y cierres) con foto obligatoria por muestreo.</td></tr>
<tr><td>evidence_retention_days</td><td>180</td><td>Días que se conservan las fotos.</td></tr>
<tr><td>gps_retention_days</td><td>90</td><td>Días que se conservan los pings GPS.</td></tr>
<tr><td>daily_sales_target_default_cents</td><td>234000 ($2,340)</td><td>Meta diaria cuando el punto no tiene una propia.</td></tr>
<tr><td>shift_reopen_window_hours</td><td>24 (1–48)</td><td>Horas tras el cierre en que aún puedes "Continuar turno" (además debe ser del mismo día).</td></tr>
<tr><td>inventory_count_tolerance_units</td><td>3</td><td>Diferencia entre conteo y teórico que abre caso de inventario.</td></tr>
</table></div>
<p>Precedencia: override en <b>Reglas</b> (params) &gt; Parámetros &gt; valor por defecto. Cada guardado: toast <i>"Parámetro X guardado"</i> y entrada <code>settings.update</code> en el audit log. Un valor fuera de rango devuelve un error como <i>"photo_sampling_pct debe ser ≤ 100"</i>.</p>
"""

ADM_DETAIL = """
<h3 id="adm-usuarios">Usuarios y dispositivos</h3>
<p><b>Usuarios</b>: usuario (no se cambia), nombre, rol (Operador, Supervisor, Operaciones, Finanzas, Administrador), contraseña, zona, teléfono, activo. Badge <span class="badge b-amber">Debe cambiar contraseña</span> tras un restablecimiento. <span class="ui">Restablecer contraseña</span> genera una temporal, cierra todas sus sesiones y obliga a cambiarla al entrar; se muestra una sola vez con botón <span class="ui">Copiar</span>. La baja es lógica: el usuario deja de poder entrar, su historia se conserva.</p>
<p><b>Dispositivos</b>: nombre/ID, usuario, plataforma, último login y visto. <span class="ui r">Revocar</span> pide motivo (por defecto "Dispositivo perdido") e invalida la sesión al instante (la PWA recibe DEVICE_REVOKED y cierra sesión sin borrar su cola cifrada); <span class="ui">Reactivar</span> la vuelve a permitir.</p>

<h3 id="adm-puntos">Zonas, puntos, carritos y asignaciones</h3>
<ul>
<li><b>Zonas</b>: nombre y activa; muestra cuántos supervisores y puntos tiene. El supervisor sólo ve su zona.</li>
<li><b>Puntos</b>: nombre, dirección, latitud/longitud, <b>geocerca (m)</b> (radio para "En geocerca / Fuera"; 150 m en demo), zona, horario de apertura/cierre, meta diaria ($) y meta de transacciones.</li>
<li><b>Carritos</b>: código (C-001…) y descripción. Un carrito sólo puede tener un turno abierto a la vez.</li>
<li><b>Asignaciones</b>: operador + punto + carrito + fecha (una por operador y día). Estado <code>planned</code> → <code>started</code> (al abrir) → <code>done</code> (al cerrar) o <code>absent</code>. Columna <b>Turno</b> con el estado del último turno y botón <span class="ui p">Continuar turno</span> si está cerrado.</li>
</ul>

<h3 id="adm-precios">Presentaciones y versiones de precio</h3>
<p><b>Presentaciones</b>: nombre, gramos, orden, activa; columna "Precio vigente". <b>Precios</b>: cada cambio es una <b>nueva versión</b> con vigencia; las ventas guardan la versión usada (nunca se reescriben). <span class="ui p">+ Nueva versión</span> pide nombre y un precio por presentación y queda vigente ahora. <span class="ui">Desactivar</span> advierte: los operadores sin señal seguirán vendiendo con esos precios hasta sincronizar; el servidor acepta esas ventas <b>72 h</b> y las marca "precio vencido" en el reporte. Asegúrate de tener otra versión activa.</p>
""" + fig(flow([("v1 vigente", "$25 · $35 · $45", GRAY), ("+ Nueva versión v2", "$28 · $38 · $48 · vigente ahora", ORANGE), ("Desactivar v1", "confirmación", AMBER), ("72 h de gracia", "ventas offline con v1 aceptadas y marcadas", BLUE), ("Reporte", "columna 'Precio vencido'", GREEN)]), "Ciclo de un cambio de precio. Las ventas históricas conservan la versión con la que se hicieron.") + """
<h3 id="adm-reopen">Continuar turno (reabrir un turno terminado)</h3>
<p>Disponible en <b>Control Tower</b> (sólo con la fecha de hoy, en filas con turno Cerrado) y en <b>Asignaciones</b>. Modal <i>"Continuar turno terminado"</i>: explica el efecto, pide <b>motivo</b> (5–280 caracteres) y confirma con <span class="ui p">Reabrir turno</span>.</p>
""" + fig(states({"c": (120, 60, "Cerrado", BLUE), "o": (420, 60, "Abierto", GREEN), "c2": (760, 60, "Cerrado (2º cierre)", BLUE), "x": (420, 190, "Rechazado 409", RED)}, [("c", "o", "Reabrir turno + motivo"), ("o", "c2", "operador cierra de nuevo"), ("c", "x", "no es de hoy · > ventana · otro turno abierto · transferido")], h=240), "Reglas de la reapertura. El sistema conserva íntegro el cierre anterior en el audit log.") + """
<div class="tbl"><table><tr><th>Condición</th><th>Mensaje si no se cumple</th></tr>
<tr><td>El turno está <code>closed</code> (no transferido)</td><td>"Sólo se puede continuar un turno cerrado (no transferido ni abierto)"</td></tr>
<tr><td>Se abrió hoy (día local)</td><td>"Sólo se puede continuar un turno abierto hoy"</td></tr>
<tr><td>Cerró hace menos de <code>shift_reopen_window_hours</code></td><td>"El turno se cerró el 04-sep 10:34 (hace 14 h 2 min; servidor: 05-sep 00:36) y la ventana es de 24 h…" — si las horas no cuadran, revisa el reloj del servidor o del teléfono</td></tr>
<tr><td>Ni el operador ni el carrito tienen otro turno abierto</td><td>"El operador ya tiene otro turno abierto" / "El carrito ya tiene otro turno abierto"</td></tr>
</table></div>
<p><b>Qué hace</b>: el mismo turno vuelve a <i>abierto</i> (caja y asistencia reabiertas, asignación a <code>started</code>); las ventas se conservan; los casos de diferencia de caja / inventario y la aprobación pendiente de ese cierre se marcan <b>superados</b> (caso cerrado, aprobación <span class="badge b-gray">Cancelada</span>) con tu motivo; evento <code>ShiftReopened</code> y audit <code>shift.reopen</code> con el cierre anterior completo. El operador ve el puesto abierto al volver a su app (o en menos de 60 s) con el acumulado de ventas, y al cerrar de nuevo se concilia todo el día.</p>

<h3 id="adm-reglas">Reglas y Parámetros</h3>
<p>Ver el manual de Operaciones para la tabla de reglas. Como administrador eres el único que edita <b>Parámetros</b>; Operaciones y Finanzas los ven en lectura. Los umbrales de caja e inventario los heredan las reglas salvo override.</p>

<h3 id="adm-audit">Audit log</h3>
<p>Acciones que generas: <code>users.create/patch/delete</code>, <code>password.reset</code>, <code>device.revoke</code>, <code>price_version.create/patch</code>, <code>settings.update</code>, <code>rule.update</code>, <code>shift.reopen</code>, <code>approval.decide</code>, <code>approval.cancel</code>. Cada una con antes/después, motivo, IP y dispositivo.</p>
"""

ADM_STEPS = """
<h3 id="adm-ej1">Ejemplo 1 · Puesta en marcha de una zona nueva</h3>
<ol class="steps">
<li><b>Zona</b> Zonas → + Nuevo → "Norte" → Crear.</li>
<li><b>Puntos</b> Puntos → + Nuevo → "Metro Indios Verdes", dirección, lat 19.4956, lng −99.1195, geocerca 150, zona Norte, 08:00–18:00, meta $2,600, 65 tx.<div class="ex">Si dejas la meta vacía se usa daily_sales_target_default_cents ($2,340).</div></li>
<li><b>Carrito</b> Carritos → + Nuevo → C-004.</li>
<li><b>Usuarios</b> Supervisor "sup2" (rol Supervisor, zona Norte) y operador "op4" (rol Operador, zona Norte, contraseña inicial).<div class="ex">Comparte la contraseña por un canal seguro; el operador entra sólo desde la PWA en https.</div></li>
<li><b>Asignación</b> Asignaciones → + Nuevo → op4 · Metro Indios Verdes · C-004 · fecha de hoy → Crear.<div class="ex">"Al crear sin horario, se usa el horario de apertura/cierre del punto." A partir de la hora de apertura + 20 min sin abrir, la regla "Punto sin abrir" avisará a sup2.</div></li>
</ol>

<h3 id="adm-ej2">Ejemplo 2 · Subir precios el lunes</h3>
<ol class="steps">
<li><b>Nueva versión</b> Precios → <span class="ui p">+ Nueva versión</span> → Nombre "v2 septiembre" → 50 g $28 · 75 g $38 · 100 g $48 → <span class="ui p">Crear versión (vigente ahora)</span>.<div class="ex">Toast "Versión de precio creada". La PWA toma los precios nuevos en su siguiente sincronización.</div></li>
<li><b>Desactivar v1</b> Fila v1 → <span class="ui">Desactivar</span> → lee la advertencia de las 72 h → aceptar.<div class="ex">Un operador sin señal que vendió a $25 esa mañana sincroniza a mediodía: la venta se acepta y en Ventas aparece "1 vencido".</div></li>
<li><b>Verifica</b> Precios muestra v2 Activa con "Ventas: 37" al final del día; v1 "Desactivada 09/08 08:02".</li>
</ol>

<h3 id="adm-ej3">Ejemplo 3 · Operador cerró por error a las 11 a.m.</h3>
<ol class="steps">
<li><b>Control Tower</b> (fecha de hoy) fila Metro Insurgentes: Estado Cerrado, Caja OK. Acción <span class="ui p">▶ Continuar turno</span>.</li>
<li><b>Motivo</b> "El operador cerró por error a media jornada; continúa hasta las 6 pm" → <span class="ui p">Reabrir turno</span>.<div class="ex">Toast "Turno reabierto: Metro Insurgentes. El operador puede seguir vendiendo." La fila pasa a Abierto y el botón desaparece.</div></li>
<li><b>En el teléfono</b> El operador abre la app: "Puesto abierto · $70 · 2 ventas". Sigue vendiendo.</li>
<li><b>Si sale un 409</b> "El turno se cerró el 04-sep 10:34 (hace 14 h 2 min; servidor: 05-sep 00:36)…" y apenas son las 12:40: el reloj del servidor está mal. Corrige la hora/zona de la VM antes de reintentar.</li>
<li><b>Trazabilidad</b> Audit log → Entidad shift → acción <code>shift.reopen</code>: antes (closed_at, contado, diferencia, product_diff) → después (open, casos y aprobaciones superados), tu usuario, IP y motivo.</li>
</ol>

<h3 id="adm-ej4">Ejemplo 4 · Teléfono robado</h3>
<ol class="steps">
<li><b>Revocar</b> Dispositivos → fila del operador (último visto hace 40 min) → <span class="ui r">Revocar</span> → motivo "Robo reportado 5 p.m." → aceptar.<div class="ex">"Dispositivo revocado". Cualquier petición desde ese teléfono recibe 401 DEVICE_REVOKED; la app muestra "Este teléfono fue dado de baja. Avisa a tu supervisor."</div></li>
<li><b>Contraseña</b> Usuarios → <span class="ui">Restablecer contraseña</span> → copia la temporal → entrégala en persona.<div class="ex">El operador entra desde otro teléfono, la app le exige cambiarla ("Cambia tu contraseña") y luego trabaja normal.</div></li>
<li><b>Turno abierto en el teléfono robado</b> Si el turno quedó abierto, el supervisor puede transferirlo o esperar el cierre desde el nuevo teléfono (la app adopta el turno abierto del servidor al entrar).</li>
</ol>
"""

MANUALS = {
    "operador": ("operator", "Operador", "Cómo usar la app del teléfono para abrir el puesto, vender, pedir ayuda y cerrar caja, con o sin señal.", [
        {"id": "que", "title": "Qué puedes hacer", "html": OP_INTRO},
        {"id": "rapida", "title": "Guía rápida", "html": OP_QUICK},
        {"id": "detalle", "title": "Detalle de cada pantalla", "html": OP_DETAIL},
        {"id": "pasos", "title": "Paso a paso con ejemplos", "html": OP_STEPS},
    ], "PWA Operador · teléfono · funciona sin señal"),
    "supervisor": ("supervisor", "Supervisor", "Cómo atender los casos de tu zona por prioridad, planear la ruta y auditar en sitio.", [
        {"id": "que", "title": "Qué puedes hacer", "html": SUP_INTRO},
        {"id": "rapida", "title": "Guía rápida", "html": SUP_QUICK},
        {"id": "detalle", "title": "Detalle de cada pantalla", "html": SUP_DETAIL},
        {"id": "pasos", "title": "Paso a paso con ejemplos", "html": SUP_STEPS},
    ], "Backoffice · teléfono o computadora · sólo tu zona"),
    "operaciones": ("ops", "Operaciones", "Cómo monitorear toda la red desde el Control Tower, ajustar las reglas y gestionar inventario, activos y mantenimiento.", [
        {"id": "que", "title": "Qué puedes hacer", "html": OPS_INTRO},
        {"id": "rapida", "title": "Guía rápida", "html": OPS_QUICK},
        {"id": "detalle", "title": "Detalle de cada pantalla", "html": OPS_DETAIL},
        {"id": "pasos", "title": "Paso a paso con ejemplos", "html": OPS_STEPS},
    ], "Backoffice · toda la red"),
    "finanzas": ("finance", "Finanzas", "Cómo decidir aprobaciones, revisar caja y ventas, y auditar cambios.", [
        {"id": "que", "title": "Qué puedes hacer", "html": FIN_INTRO},
        {"id": "rapida", "title": "Guía rápida", "html": FIN_QUICK},
        {"id": "detalle", "title": "Detalle de cada pantalla", "html": FIN_DETAIL},
        {"id": "pasos", "title": "Paso a paso con ejemplos", "html": FIN_STEPS},
    ], "Backoffice · toda la red · lectura + aprobaciones"),
    "administrador": ("admin", "Administrador", "Cómo configurar usuarios, puntos, precios y parámetros, y resolver las excepciones que sólo el administrador puede.", [
        {"id": "que", "title": "Qué puedes hacer", "html": ADM_INTRO},
        {"id": "rapida", "title": "Guía rápida", "html": ADM_QUICK},
        {"id": "detalle", "title": "Detalle de cada pantalla", "html": ADM_DETAIL},
        {"id": "pasos", "title": "Paso a paso con ejemplos", "html": ADM_STEPS},
    ], "Backoffice · todos los permisos"),
}
