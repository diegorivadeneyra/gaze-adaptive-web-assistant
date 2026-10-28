# gaze-adaptive-web-assistant

Sistema de asistencia web adaptativa basada en la atención visual del usuario.

## Instalación (otra computadora)

> **Guía paso a paso para las pruebas con participantes** (instalación, cada sesión,
> resultados y problemas frecuentes): [`GUIA_PRUEBAS.md`](GUIA_PRUEBAS.md).

1. Instalar **Ollama** (el instalador, no es un paquete pip): https://ollama.com/download
2. Instalar las dependencias de Python:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Correr el backend:
   ```bash
   cd backend
   python app.py
   ```
   La primera vez, el backend descarga solo los modelos que falten en Ollama
   (`phi3` para texto y `qwen2.5vl:3b` para imágenes y gráficas, ~5.5 GB en total).
   Los modelos corren localmente: sin API key ni límites de uso.
4. Abrir `http://127.0.0.1:5000/` en el navegador.

**Con el Tobii 5 (laptop de las pruebas):**
- Instalar el software del Tobii (**Tobii Experience**) y calibrar a cada persona ahí.
- El puente `tobii_bridge/bin/gaze_server.exe` **ya viene compilado** en el
  repositorio (versión Release, no necesita Visual Studio) y `app.py` lo abre
  solo en otra ventana. Solo hay que recompilarlo si cambia `gaze_server.cpp`.
- En `backend/app.py`: `GAZE_INPUT_SOURCE = INPUT_SOURCE_TOBII`.
- Navegador en la pantalla del Tobii, con zoom al 100 %; la comprobación de 5
  puntos al inicio de cada sesión ajusta lo demás (resolución, escala de Windows).
- Primera vez: correr `python app.py` con internet para que Ollama descargue los
  modelos (~5.5 GB); después funciona sin internet.

No se suben a git (ver `.gitignore`): `data/` (sesiones y respuestas de
participantes), `respaldos/` (diseño anterior, solo en la PC original) y
material de referencia suelto.

## Fuente de coordenadas (mouse / Tobii 5)

Se elige en `backend/app.py` con `GAZE_INPUT_SOURCE` (`INPUT_SOURCE_MOUSE` o
`INPUT_SOURCE_TOBII`). Para usar el Tobii 5, ver `tobii_bridge/README.md`.
Con `?debug=0` en la URL se oculta el panel de monitoreo (para las sesiones con
participantes, de modo que no sesgue su atención).

## Sesiones con participantes (registro)

1. Correr `python app.py` (uno solo) y abrir `http://127.0.0.1:5000/` (el índice).
2. En **Sesión experimental**, escribir el código del participante (`P01`, nunca
   el nombre). Se sugiere la condición de cada página según el número (ver
   sección 8); se puede cambiar. "Ocultar panel de monitoreo" viene marcado.
3. **Iniciar sesión** lleva a la página fácil. Al terminar, volver al índice y
   pulsar **Finalizar sesión**.

Sin sesión iniciada las páginas funcionan en **modo libre**: ayuda siempre activa
y nada se registra (para desarrollo y demos).

**Diseño final (2026-10-20, acordado con la asesora): se comparan DOS métodos,
ayuda automática y ayuda a pedido** ("sin ayuda" ya no se usa en las pruebas;
el código lo sigue aceptando). El **orden de las páginas es aleatorio** para
cada participante. Métodos: la página **fácil siempre "a pedido"** (casi no tiene
párrafos difíciles: con la ayuda automática nunca aparecería ayuda); **intermedia y
avanzada al azar, una con cada método**, así cada persona prueba los dos. `index.html` sortea y permite volver a sortear o ajustar; el orden se
guarda en la sesión (`order`), la navegación lo sigue (`marking.js`) y
`paginas.csv` tiene la columna `posicion` (1, 2 o 3). Probado en el navegador.

**Pantallas para el participante (2026-10-20):** al pulsar "Iniciar sesión", el
investigador ve una **pantalla de bienvenida** que tapa los parámetros (las mismas
instrucciones para todos, sin mencionar niveles ni métodos); el participante pulsa
**Iniciar** y va a la primera página sorteada. Al terminar la última página, una
**pantalla de cierre** pide responder las hojas del Excel (con un
botón pequeño para que el investigador vea la sesión y la finalice).
**Tooltip:** al apartar la mirada se mantiene 2.5 s (`TOOLTIP_HOLD_MS`) en todas las
condiciones y con mouse o Tobii (antes, en "automática" con mouse se ocultaba al
instante); si la mirada vuelve en ese lapso al mismo elemento (párrafo, tabla o
gráfica), sigue visible. Probado con reloj controlado.

**Pausa entre páginas (2026-10-20; descanso obligatorio desde el 2026-10-25):** al
pulsar "Terminé esta página" se cierra el tiempo de lectura (`reading_end`), la
persona **marca** lo que le costó entender y luego viene un **descanso de 1.5 minutos**
que **tapa el texto** y **no pide nada**: ni botones ni cuestionarios (todo va al
final, después de las 3 páginas). Una cuenta regresiva lo muestra y al terminar pasa
**sola** a la siguiente página. Tras la última página no hay descanso: va al cierre.
Por qué 1.5 min (era 2 min; el usuario lo bajó el 2026-10-25): cada lectura dura ~2–5 min (367 / 502 / 666 palabras a 150–200
palabras por minuto, más el tiempo con la ayuda). **Tiempo máximo de lectura
(2026-10-28, pedido del usuario): fácil 4 min, intermedia 7 min, avanzada 10 min**
(`READING_LIMIT_MS` en `marking.js`, contados desde que carga la página), **sin aviso
previo** (se probó un aviso un minuto antes y el usuario lo quitó). Al cumplirse pasa
lo mismo que con "Terminé esta página" (marcado de lo difícil → descanso), con la
barra "Se acabó el tiempo de esta página". `reading_end` lleva `timed_out` y
`limit_ms`; `paginas.csv` la columna `lectura_por_tiempo` (1/0). Antes la lectura no
tenía límite, para no forzar el ritmo natural del que depende la ayuda; con estos
máximos (más del doble de la lectura estimada) solo debería cortarse a quien se
quede mucho tiempo en una página. Probado en el navegador con el límite reducido a
15 s. Sesión completa ≈ 25–30 min sin los cuestionarios (máximo ≈ 25 min de
lectura; comprobación de la mirada ~1 min, 3 lecturas, 2 descansos). `PAUSE_MS` en `marking.js`. **Botón "Saltar descanso" (2026-10-26)** junto a la
cuenta regresiva: pasa de inmediato a la siguiente página; `pause_end` lleva `skipped`
y `paginas.csv` la columna `pausa_saltada` (1/0). Durante el descanso **no se registra nada**
(ni la mirada), solo su inicio y fin. `paginas.csv`: `duracion_ms` = solo la
lectura; `pausa_ms` = el descanso. (Antes el marcado iba después de la pausa y la
pausa terminaba con un botón "Listo".) En el
Excel, las secciones de comprensión tienen títulos neutros por tema ("El hielo
del planeta"…): "Página fácil" revelaba el nivel.

**Nada en pantalla revela el nivel (2026-10-22/25):** los archivos se llaman
**`siteA.html` (fácil), `siteB.html` (intermedia) y `siteC.html` (avanzada)**
(`PAGE_URLS` en `session.js`), porque la barra de direcciones mostraba `facil.html`;
en el registro y el análisis la página sigue siendo `facil`/`intermedio`/`avanzado`.
La barra de navegación interna dice "Sitio A/B/C". Se
quitaron los enlaces Fácil/Intermedio/Avanzado del pie de página (además dejaban saltar a
otra página) y el nombre "EcoFácil" pasó a "EcoPlaneta". La barra de niveles de arriba
sigue oculta en sesión. Probado en el navegador con una sesión completa (borrada).

**Sorteo PREVIO y balanceado (2026-10-25):** el orden de páginas y el método de cada
participante se fijan antes del piloto con `python evaluation/generar_asignacion.py`
(semilla fija, reproducible) → `frontend/js/asignacion.js` y
`evaluation/asignacion_participantes.csv`. Al escribir un código de la lista
(P01…P06) en el inicio, el orden y los métodos quedan fijos (no editables); otro código
(p. ej. una prueba) se sortea al momento, como antes. Fácil sigue siempre "a pedido" y
**no entra en la comparación de métodos**; en intermedia y avanzada cada participante
lee una con cada método. **Piloto con N = 6** (decidido el 2026-10-25): cada uno de
los 6 órdenes de páginas se usa una vez (cada página cae 2 veces en cada posición) y
cada método tiene **6 lecturas** (automática: 3 en intermedia + 3 en avanzada; igual a
pedido). Además, la página automática se lee **antes** que la de "a pedido" en 2 de
los 6 y **después** en 4 (con 6 no puede ser 3/3 a la vez que 3/3 por página; lo más
parejo posible). Sin esa condición, la primera semilla dejaba la automática siempre
primero: el método se habría confundido con el orden. Con 12 personas
(`N_BLOCKS = 2`) todo queda en mitades exactas.

Condiciones que existen en el sistema (desde el 2026-10-17):

| Condición (valor en el plan) | Qué ve la persona |
|---|---|
| **Sin ayuda** (`sin_ayuda`) | Nada. El sistema funciona igual y registra la ayuda que *habría* mostrado (`help_suppressed`) |
| **Automática** (`ayuda`) | La ayuda aparece sola cuando la conducta de lectura lo indica |
| **A pedido** (`a_pedido`) | Apenas el análisis dice que hay ayuda, aparece un botón **💡 Ver ayuda** en el lugar del tooltip; al hacer clic se muestra la ayuda, y **📘 Más detalle** da la explicación ampliada. La regla automática corre en silencio (`help_suppressed`), para comparar lo que la persona pide con lo que el sistema detecta |

Eventos nuevos: `help_offered` (botón mostrado) y `help_requested` (clic). En
`paginas.csv`: `botones_ofrecidos`, `ayudas_pedidas`, `elementos_pedidos` y
`pedidos_que_la_regla_detecto` (validación del detector); en `ayudas.csv`, la
columna `pedida`. Probado en el navegador con una sesión de prueba (borrada).

**Cuestionarios (Excel, 2026-10-20 según el protocolo CIEI-UTEC):** cada
participante responde su propio Excel, `data/respuestas/P01.xlsx`…, que crea
`python evaluation/crear_cuestionarios_excel.py` a partir del sorteo (sin pisar los que
ya existen; la plantilla queda en `evaluation/cuestionarios_participante.xlsx`). **Todo se
responde al final**, después de las 3 páginas (cambio del 2026-10-22: en las
pausas no se puede aplicar ningún cuestionario), en este orden: **Comprensión**
por **recuerdo libre** (desde el 2026-10-25: un recuadro por página, numeradas en el orden
en que esa persona las leyó —"Página web 1 (la primera que leíste)"—, sin títulos, para
escribir con sus palabras lo que entendió; reemplaza a las 12 preguntas de opción
múltiple de `prueba_comprension.md`), **un NASA-TLX del Anexo 3 por método**
(hojas «NASA-TLX Método 1» y «NASA-TLX Método 2»; 6 dimensiones, 15 comparaciones
por pares y definiciones) y el **post-experimento del Anexo 4** adaptado
a 2 métodos (Método 1 = automática, Método 2 = a pedido). **Anexo 4 adaptado a la lectura
(2026-10-25; avisar a la asesora/CIEI):** el original era de una técnica de interacción
con la mirada. Orden de métodos: "más rápido" → ayuda en mejor momento; "menos errores"
→ entendiste mejor; "para comunicarte" → para leer textos difíciles ("más cómodo" igual).
Calificación 1–5: "rendimiento" → te ayudó a entender; "reducción de errores" → utilidad
de las explicaciones; "precisa" → la ayuda apareció cuando la necesitabas; "agradables las
interfaces" → agradable leer con el método; confianza, aprender y vida diaria iguales
(esta última "al leer en internet"); nueva: **¿qué tanto te distrajo o interrumpió la
ayuda?** (inversa: alto = negativo), el costo de interrupción que discute la tesis. Diseño: en las escalas
de 1 a 5 (calificaciones y orden de métodos) se muestra al inicio qué significa
cada número y las opciones lo incluyen ("4 = Alto"; la puntuación lee el
número); en el NASA-TLX las definiciones del Anexo 3 van junto a cada dimensión.
**Cambio del 2026-10-27 (pedido del usuario): se quitó el SUS y el NASA-TLX se duplicó,
uno por método** (antes era uno solo sobre toda la tarea). Cada hoja dice en qué página
pensar ("Fue la página web 3, la tercera que leíste"), tomada del sorteo: Método 1 = la
página con ayuda automática; Método 2 = la **intermedia o avanzada** leída a pedido (la
fácil también es "a pedido", pero no entra en la comparación de métodos). Para un código
fuera del sorteo: `--automatica intermedio|avanzado`. Así el NASA-TLX compara la carga de
los dos métodos dentro de cada persona; costo: compara además páginas distintas
(intermedia vs. avanzada), que el sorteo reparte entre métodos. La comprensión de la primera página leída se responde más tarde (más olvido;
el orden aleatorio lo reparte entre métodos). Una hoja oculta `_mapa`
dice qué celda tiene cada respuesta. El archivo que se guarda como `data/respuestas/P01.xlsx` (el código igual
al de la sesión; `data/` está fuera de git). `python evaluation/puntuar_cuestionarios.py`
lee todos y genera en `data/sessions/resumen/`: `comprension_textos.csv` (por
participante y página: el texto escrito, su número de palabras y columnas para
**calificarlo a mano**: `ideas_correctas`, `ideas_incorrectas`, `notas`; al volver a
correr el script, lo ya calificado se conserva), `nasa_tlx.csv` (una fila por participante y
método: bruto y **ponderado**, con los pesos),
`post_experimento.csv`, `post_metodos.csv` (una fila por método, con su NASA) y `avisos.txt`
(respuestas vacías, empates en el orden de métodos, archivos de versiones
anteriores). Probado con Excel de prueba: NASA ponderado calculado a mano 34.0 =
34.0 del script; con la versión por método (2026-10-27), un Excel lleno con 50 en el
Método 1 y 70 en el Método 2 dio 50.0 y 70.0, sin avisos.

**Versión final del Excel (2026-10-28):** el usuario editó a mano la plantilla
`evaluation/cuestionarios_participante.xlsx` y es la que responden todos (se entrega por
Drive). Post-experimento: 4 órdenes (ayuda más rápida, más cómodo, mayor control,
elegiría) y 7 calificaciones (completar la tarea, comodidad, **aprender — solo 1 o 5**,
rapidez, precisión, confianza, uso futuro); ya no está "distracción". Se reescribió su
`_mapa` (las claves `resumen_pos1..3` de comprensión van por posición, y los
comentarios habían subido una fila) y `puntuar_cuestionarios.py` traduce la posición
a la página con el orden del participante (sorteo; si no, su `session_start`).
`crear_cuestionarios_excel.py` ya no reescribe la plantilla. Probado con tres Excel
llenos (código del sorteo, código con sesión y código sin orden): páginas, NASA por
método, órdenes, calificaciones y comentarios leídos en su lugar.

**Antes de cada sesión:** arrancar `python app.py` y esperar el mensaje
`[WARMUP] Modelos listos.` (~20 s). Medido el 2026-10-17: sin ese
precalentamiento, la primera ayuda salía con el mensaje genérico mientras phi3
cargaba (el precalentamiento de texto no llegaba a phi3; corregido).

**Equipos con GPU de 6 GB (laptop de las pruebas, RTX 3050; 2026-10-25):** phi3
(2.6 GB) y Qwen (2.7 GB) no caben juntos y Ollama descarga uno para cargar el otro.
Medido en la laptop: phi3 cargado 3.9 s; Qwen tras phi3 7.9 s; phi3 tras Qwen 11.7 s
(cerca del límite de 15 s, con riesgo de mensaje genérico). Ajustes: el arranque
deja cargado phi3 (el más usado; Qwen solo analiza 4 gráficas), phi3 se recarga en
segundo plano después de cada análisis de gráfica (`reload_text_model`) y el límite
de espera del texto subió de 15 a 25 s (`TEXT_TIMEOUT_S`). En la PC (8 GB) no cambia nada.

**Gráficas: el análisis no se cancela al apartar la mirada (2026-10-25).** En la sesión
de prueba en la laptop, una gráfica de la página avanzada se miró 8 veces (28 s en
total, ~3.5 s cada vez) y nunca se analizó: en esa GPU el análisis visual tarda ~11 s
y se cancelaba en cada salida. Ahora, en figuras (no en texto), el análisis sigue
hasta terminar, queda guardado y, al volver, la ayuda aparece al instante; si se
vuelve antes de que termine, se espera el mismo análisis (no se pide otro). El
registro marca `background: true` en el evento `analysis` cuando terminó con la mirada
en otro elemento. En texto se mantiene la cancelación (si no, al saltar entre
párrafos se acumularían análisis). Probado en el navegador con mirada simulada.

Cada sesión queda en `data/sessions/` (fuera de git: son datos de participantes):

| Archivo | Contenido |
|---|---|
| `<sesion>_events.jsonl` | Un evento por línea: `session_start` (plan, modelos, política de ayuda, commit del código), `page_enter` (condición, pantalla, parámetros de mirada, hash del texto de la página), `layout` (posición de cada elemento), `element_enter`/`element_exit` (dwell, número de visita), `analysis` (nivel, fuente, INFLESZ, nivel del modelo, explicación, latencia), `help_shown`/`help_suppressed`, `help_hidden` (tiempo visible y tiempo con la mirada dentro), `page_exit`, `session_end` |
| `<sesion>_gaze.csv` | Muestras crudas (`t_ms, x, y, scroll_x, scroll_y, valid, page`), incluidas las inválidas del Tobii (parpadeos), para recalcular dwell y umbrales sin repetir participantes |

`python evaluation/analyze_sessions.py` arma `data/sessions/resumen/`:
`visitas.csv` (una fila por visita a un elemento), `ayudas.csv` (cada ayuda con
su texto y una columna `calificacion` para calificarla a mano) y `paginas.csv`
(una fila por participante y página, la unidad de comparación de la sección 8).

Detalles: los eventos se envían cada 2 s y al salir de la página
(`sendBeacon`); si el backend no responde se reintenta sin perder el orden. Los
elementos se identifican por su ruta en el DOM (sirve en cualquier página sin
anotarla); si se edita el contenido de una página cambian las rutas, por eso se
registra el hash del texto. Con mouse se registran solo los movimientos reales
(pocas muestras si el cursor está quieto); con el Tobii, ~90 Hz.
**Probado** con dos sesiones de mouse (con y sin ayuda): eventos, tablas y
supresión de la ayuda funcionaron; con el Tobii aún no (está prestado).

---

## Criterios para la experimentación

> **Referencia rápida de todas las reglas** (cuándo se analiza, cómo se decide el
> nivel, cuándo se muestra la ayuda, cómo se mide si sirve y cómo se comparan
> mejoras): [`REGLAS_DEL_SISTEMA.md`](REGLAS_DEL_SISTEMA.md).
> **Resumen por componente con sus pruebas** (dwell time, I-DT, modelos,
> latencias, qué está probado y qué no): [`RESUMEN_DEL_SISTEMA.md`](RESUMEN_DEL_SISTEMA.md).

Este apartado documenta **cómo se fijó cada parámetro y umbral** que decide si
el sistema ofrece ayuda y cómo se distingue el nivel de dificultad. Cada valor
indica su origen: *estándar publicado*, *medido en este proyecto* o *criterio de
diseño inicial* (a calibrar con las pruebas piloto). No se afirma más respaldo
del que existe.

### 1. Nivel de dificultad del contenido (Low / Medium / High)

| Contenido | Cómo se mide | Código |
|---|---|---|
| Texto corrido en español, ≥ 8 palabras | Índice de legibilidad **INFLESZ** (Szigriszt-Pazos) | `backend/analyzers/readability.py` |
| Texto < 8 palabras (títulos, etiquetas) y **tablas** | Juicio del modelo de lenguaje (phi3) | `backend/analyzers/text_analyzer.py` |
| **Gráficas con nivel diseñado** (atributo `data-design-level` en el HTML) | **Nivel diseñado** del estímulo; el modelo de visión solo redacta la ayuda | `backend/analyzers/image_analyzer.py` (`apply_design_level`), `frontend/js/gaze.js` (`getDesignLevel`) |
| **Imágenes y gráficas sin nivel diseñado** | Juicio del modelo de visión (qwen2.5vl:3b), con el pie de figura como contexto | `backend/analyzers/image_analyzer.py` |

**Nivel diseñado de las gráficas (criterio de diseño del estímulo, no
detección).** Cada gráfica lleva el nivel con el que se diseñó su página:
intermedio → `Medium`, avanzado → `High`. El sistema **no detecta** ese nivel:
lo declara el investigador, igual que declara el nivel de cada página. Se
adoptó porque el juicio del modelo sobre gráficas **no es válido** como
criterio (medido, ver sección 7): con temperatura 0 es estable dentro de una
corrida, pero cambia con detalles ajenos a la gráfica: pasar el prompt a
español llevó la gráfica de avanzado de *Medium* a *Low* (sin ayuda), y el
mismo prompt sin pie de figura dio *Low* 3/3 un día y *Medium* 3/3 al
siguiente. Detalles:
- Lo que dice el modelo se guarda en `llm_complexity` para medir el acuerdo
  (en las mediciones: intermedio coincide 3/3; avanzado, el modelo dice *Low*
  3/3 frente al *High* diseñado).
- Con nivel diseñado `Low` no se llama al modelo (respuesta instantánea, como
  el texto fácil por legibilidad).
- El prompt de visión **no se cambió**. Se probó pedir "explicación obligatoria"
  para que nunca saliera vacía y alargó la explicación de intermedio de 19 a 46
  palabras, hasta cortarse por el tope de tokens. Con el prompt actual Qwen
  escribe la explicación aunque juzgue *Low* (3/3); si alguna vez llega vacía,
  se usa un texto genérico de respaldo en vez de un tooltip vacío.
- El atributo se llama `data-design-level` y no `data-level` porque `<body>`
  ya usa `data-level` para el estilo de la página (se detectó en la prueba en
  el navegador: la foto heredaba "advanced").
- Las **fotografías** (glaciares, la Tierra) no llevan nivel diseñado y siguen
  con el juicio del modelo. *Pendiente de decidir.*

**Fórmula:** `INFLESZ = 206.835 − 62.3 · (sílabas / palabras) − (palabras / oraciones)`.
**Cortes** (los estándar de la escala INFLESZ, agrupados en los tres niveles):

| INFLESZ | Etiqueta INFLESZ | Nivel del sistema |
|---|---|---|
| ≥ 55 | normal o más fácil | **Low** (sin ayuda) |
| 40 – 55 | algo difícil | **Medium** |
| < 40 | muy difícil | **High** |

**Por qué legibilidad y no solo el modelo:** es determinista (el mismo texto
recibe el mismo nivel en todos los participantes), explicable, gratuita, y
permite no llamar al modelo cuando el texto es fácil (respuesta instantánea).
El juicio del modelo es subjetivo y poco estable: en una prueba, una frase
claramente fácil ("El hielo del Ártico ocupa hoy menos espacio que hace 40
años") fue calificada *Medium* por phi3. La complejidad que dice el modelo se
conserva en `llm_complexity` para poder medir cuánto coincide con la legibilidad.

**Mínimo de 8 palabras (medido):** con 15, las frases cortas de la página fácil
(12–14 palabras) caían al juicio del modelo, que las calificaba *Medium* y daba
ayuda donde no corresponde. Con 8, 8 de esas 9 frases salen *Low* (la novena,
49.5, queda en el borde de *Medium*).

**Verificación con los niveles diseñados** (INFLESZ medido sobre el texto real
de las tres páginas):

| Página (nivel diseñado) | Bloques de texto medidos | INFLESZ observado | Nivel resultante |
|---|---|---|---|
| Fácil | 9 | 49.5 – 91.9 | 8 Low, 1 Medium |
| Intermedio | 3 párrafos | 44.7 · 52.0 · 9.6 | 2 Medium, 1 High |
| Avanzado | 3 párrafos | 18.0 · 26.1 · 39.2 | 3 High (uno en el borde) |

La medida separa los tres niveles, con excepciones. Los umbrales **no se
ajustaron** para que estas cifras salieran mejor; son los estándar.

**Limitaciones conocidas:**
- La fórmula castiga fuertemente las oraciones largas: un párrafo de
  intermedio con una sola oración de 33 palabras dio 9.6 (*High*) aunque se
  diseñó como *Medium*.
- Mide la forma del texto, no la dificultad conceptual ni el conocimiento previo
  de cada persona. Solo aplica a español; el conteo de sílabas es por reglas
  (aproximación; acertó 20 de 20 palabras de prueba).
- Tablas, imágenes y gráficas dependen del juicio del modelo, que **no está
  calibrado**. Lo medido: la cuantización a 4 bits de Qwen a veces confunde el
  orden de barras de valores parecidos (industria 10.4 vs transporte 8.2).
- Los títulos y etiquetas cortas también se envían al modelo.
- **El juicio del modelo sobre gráficas es inconsistente entre versiones del
  prompt y entre días** (ver sección 7). *Resuelto para las gráficas de los
  estímulos* con el nivel diseñado (arriba). Sigue aplicando a las fotografías
  y a cualquier figura nueva sin `data-design-level`.

### 2. Política de ayuda: cuándo se ofrece

**Desde el 2026-10-11, en texto corrido decide la conducta de la persona**:
la ayuda (disponible si el párrafo es Medium o High) se muestra solo si la
persona está **atascada** (≥ 1.5 × su tiempo de lectura esperado, a más
tardar esperado + 15 s) o **relee** un párrafo que ya había leído, sea al
volver tras salir o **sin salir** (regresión: fijaciones en su primer tercio
que suman ≥ 1.5 s). "Lo leyó" = en el último tercio con ≥ 40 % del tiempo esperado. El tiempo esperado usa sílabas, un factor por
nivel y un **ritmo que arranca en el promedio general y se adapta a la persona**
mientras lee, en cualquier página y con párrafos de cualquier nivel (desde el
2026-10-25; antes solo con párrafos fáciles). Reglas, parámetros y su origen:
[`REGLAS_DEL_SISTEMA.md`](REGLAS_DEL_SISTEMA.md) §4; código:
`decision_engine.py` (`READING_POLICY`) y `frontend/js/reading_model.js`.
La tabla de abajo (tiempo fijo por nivel) sigue aplicando a **tablas, gráficas
e imágenes**, y a todo si `/config` no responde.

Definida en un solo lugar, `backend/analyzers/decision_engine.py`
(`HELP_POLICY`); el frontend recibe los umbrales en la respuesta de `/analyze`.

| Nivel | Ayuda | Dwell mínimo en el elemento | Con relectura |
|---|---|---|---|
| Low | ninguna | — | — |
| Medium | **reactiva** | 2000 ms | 500 ms |
| High | **proactiva** | 500 ms | 500 ms |

- **500 ms (base):** equivale a ~2 fijaciones típicas de lectura (200–250 ms de
  media; Rayner, 1998): atención sostenida, no incidental. Dispara el análisis.
- **2000 ms para Medium:** *criterio de diseño inicial*, sin calibrar. La idea
  es distinguir leer de hojear (pasar la vista rápido por varios bloques).
- **High desde 500 ms:** el contenido es muy denso; esperar solo haría llegar
  la ayuda tarde.
- **Relectura:** volver a un elemento ya mirado (regresión) es una señal
  conocida de dificultad de lectura (Rayner, 1998); adelanta la ayuda *Medium*.
  La relectura se cuenta tras un cambio de elemento confirmado.
- **Matiz medido:** como el análisis tarda ~3 s, en la primera visita a un
  elemento *Medium* esos 2 s ya pasaron cuando llega la respuesta; el umbral
  pesa sobre todo en elementos ya analizados (caché por elemento).
- **Contenido de la ayuda (texto):** una definición del **término técnico más
  difícil** del texto (qué significa en palabras simples y, si ayuda, para qué
  sirve), mostrada como "Término: definición". Como la persona **ya leyó** el
  texto, la ayuda **no lo recapitula**: se le pide al modelo no repetir, resumir
  ni parafrasear, y usar solo conceptos generales sin inventar datos, cifras,
  nombres ni fechas. Sin analogías.
  - *Repetición, medida:* una versión previa pedía "qué dice el texto con eso" y
    copiaba ~11 % de los trigramas del propio texto (hasta 26 %), por ejemplo
    "El texto explica que…". La versión actual copia ~4 % (máx. 27 %).
  - *Por qué sin analogías:* en pruebas con phi3 (3.8B) salían imprecisas
    ("la sensibilidad climática es como la reacción de un termómetro al calentar
    agua") y los ejemplos libres inventaban datos que no estaban en el texto (una
    estación y un año concretos). Una analogía incorrecta en contenido científico
    confunde más que ayuda.
  - *Por qué `concept` es el término:* al hacer que el modelo elija primero un
    término concreto (antes elegía el tema general, p. ej. "cambio climático"
    en vez de "forzamiento radiativo"), la definición apunta a lo realmente difícil.
  - **Elección del término** (2026-10-11, `TERM_SELECTION = "silabas"` en
    `text_analyzer.py`): en texto corrido, el modelo propone hasta **3
    términos** con su definición y el **código elige**: descarta los que no
    están en el párrafo, los **símbolos o fórmulas** sueltos ("CO₂", "pH") y
    los **ya explicados en la misma página** (el navegador envía la lista en
    `defined_terms`), y se queda con el de la **palabra con más sílabas**
    (misma idea que INFLESZ: más sílabas por palabra = más difícil). La ayuda
    ampliada usa la misma función (`choose_terms`). Medido contra la versión
    anterior y contra "candidatos en el orden del modelo" (sección 7 y
    `evaluation/results/revision_terminos_20261011.md`). Tablas y texto en
    inglés siguen con un solo término.
  - *Longitud:* se piden ≤ 35 palabras, pero phi3 **no respeta los topes**
    (medido: pedirle 30 dio explicaciones más largas que pedirle 40). El límite
    real se aplica en código: máx. 55 palabras, recortando en el último fin de
    oración. Resultado medido: 17–47 palabras (promedio 28) en 14 corridas.
  - *Formato:* se usa un **esquema JSON estricto** en Ollama (claves y tipos
    fijos), que garantiza por construcción que exista `explanation` como texto.
    Durante el desarrollo, con `format: "json"` a secas y otra estructura de
    prompt, phi3 deformó la clave en 7 de 12 corridas ("explande"); **no se
    reprodujo** en la suite estándar (0 de 18). Se mantiene el esquema como
    medida de seguridad, sin afirmar que `json` a secas falle siempre. Si aun así
    llega como lista o numerada, se une en un párrafo.
  - Imágenes y gráficas: ≤ 25 palabras, usando solo lo visible y el pie de figura.
  - **Gráficas SVG:** además se le pasan al modelo los **textos escritos en la
    gráfica** (título, ejes, valores y etiquetas, en orden), y se le pide explicar
    qué mide (magnitud, unidad o referencia) y su patrón principal. Motivo
    (revisión del 2026-10-05): leyendo solo la imagen dijo "transporte e
    industria" en orden invertido (8.2 vs 10.4) y describía la línea sin
    explicarla. Las fotos usan el prompt de siempre (no tienen textos).
  - **Qué quiere mostrar la figura o la tabla (2026-10-26).** Pedir "qué mide"
    hacía que la ayuda de las gráficas repitiera título y unidad, o definiera un
    término; las **tablas** usaban el prompt de párrafos y definían una columna o
    sigla ("Variación respecto a 1900: es…"). Ahora las gráficas piden la
    **conclusión** según los valores (cuál es el mayor y qué tan lejos quedan los
    demás, o si aumenta o disminuye), y las tablas tienen su propio prompt
    (`build_table_prompt`): qué compara y su conclusión principal, en palabras.
    Las fotos piden la idea que ilustran según el pie. Medición en la sección 7.
- **Contexto de sección** (2026-10-06): con cada análisis de **texto y tablas**
  se envía el subtítulo de la sección donde está el elemento
  (`getSectionHeading` en `gaze.js`), presentado al modelo "solo como contexto".
  Se probaron tres variantes contra "sin contexto" (sección 7) y se eligió esta
  con un criterio fijado **antes** de medir: más cambios que mejoran que cambios
  que empeoran, y ningún párrafo High sin ayuda. El **título de la página** no
  se envía: jalaba al modelo hacia términos del título que no estaban en el
  párrafo (el párrafo "Limitaciones", High, quedaba sin ayuda en 2/2 corridas).
  Fotos y gráficas tampoco reciben contexto: empeoraba su ayuda. El backend
  sigue aceptando `page_title` (y `getPageTitle` se registra en `page_enter`).
  Los `<title>` de las páginas se cambiaron a títulos neutros para no mostrar
  "Nivel Avanzado".
- **Dónde NO se ofrece ayuda** (revisión del 2026-10-05, ver
  `evaluation/results/revision_ayudas_20261005.md`):
  - **Títulos (h1–h6):** son cortos, el modelo los juzgaba sin contexto (definió
    mal "evidencia observacional") y sus términos se repiten en el texto de
    abajo. Eran 6 de 26 ayudas. Regla general de HTML, sirve en cualquier página.
  - **Si el término definido no aparece en el texto** (`concept_in_text`, cada
    palabra de 4+ letras, sin tildes y tolerando la terminación): la ayuda se
    bloquea (`help_blocked`) aunque el nivel sea Medium/High. Evita términos
    inventados ("acumulación de energía" para una frase sobre ahorrar energía).
    Probado contra los 11 conceptos de la revisión: 11/11 bien clasificados.
  - **Notas al pie y referencias** (2026-10-11): todo lo que esté dentro de
    `.footnote`, `footer`, `cite`, `small` o roles de nota/bibliografía
    (`NO_HELP_SELECTOR` en `gaze.js`) no se analiza ni recibe ayuda. Eran 4 de
    las 17 ayudas innecesarias de la revisión del 2026-10-05. Regla de HTML
    general, no de estas páginas.
  - **Fotos** (2026-10-11): las 6 fotos llevan `data-design-level="Low"` (nivel
    con que se diseñó el estímulo, igual que las gráficas): son ilustrativas,
    no contienen datos que haya que entender. Con contexto, el modelo daba
    ayudas descriptivas a fotos de intermedio (2/2 corridas, sección 7).
  - Limitación conocida: phi3 a veces define mal un término técnico (en pruebas
    anteriores dijo que la sensibilidad climática es "la temperatura máxima que
    el clima puede alcanzar") y puede escribir con erratas. Es un límite del
    tamaño del modelo, no del prompt; uno mayor no cabe junto a Qwen en 8 GB de
    VRAM.
- **Segundo nivel: ayuda ampliada** (2026-10-11): si después de la primera
  ayuda la persona **se vuelve a trabar** en el mismo párrafo, se muestra
  (con 📘) una explicación más completa: 2–3 términos del párrafo con una
  definición breve (sin repetir el del primer nivel; cada uno pasa por
  `concept_in_text`) y "En pocas palabras:" la idea del párrafo en palabras
  simples. Aquí **sí se reformula** el texto, a diferencia del primer nivel:
  la persona ya mostró que no lo entendió ni con la definición. Se pide en
  segundo plano (`POST /expand`, `backend/analyzers/expanded_help.py`) en
  cuanto se muestra la primera ayuda, así que aparece al instante.
  "Volverse a trabar" usa las mismas señales que el primer nivel, rearmadas
  (`reading_model.rearm()`): atascado = **1.0 × esperado más** desde la
  primera ayuda (`level2_extra_fraction`, *inicial*); relectura dentro del
  párrafo = llegar otra vez al último tercio y volver al primero; relectura al
  volver = igual que antes. Medición y revisión a mano:
  `evaluation/results/revision_ayuda_ampliada_20261011.md` (sección 7).
- **Ubicación del tooltip** (2026-10-11): `computeTooltipPlacement` en
  `gaze.js` prueba, en orden, a la derecha, a la izquierda, debajo y arriba
  del elemento, y elige la primera que no tape texto, tablas, imágenes ni
  controles (un roce < 600 px² no cuenta); si todas tapan, la que menos.
  Antes el tooltip podía tapar el inicio del párrafo siguiente, y mirar ahí
  contaba como "leyendo el tooltip".
- **La ayuda reaparece tras una salida corta** (2026-10-11): si la persona ya
  tenía una ayuda en un párrafo, sale **menos de 5 s** y vuelve, la misma ayuda
  vuelve a aparecer (`reshowHelpOnReturn` en `gaze.js`). Es coherente con la
  regla de que una salida corta es la misma lectura (el tiempo sigue sumando).
  Antes quedaba sin tooltip hasta trabarse otra vez durante todo su tiempo
  esperado. Si sale **más de 5 s** y vuelve, eso es relectura y aparece el
  segundo nivel. Se registra `help_reshown` con el mismo `help_id`
  (`ayudas.csv`: columna `reapariciones`; los tiempos visibles se suman).

### 3. Captura de la mirada

| Parámetro | Valor | Criterio |
|---|---|---|
| Algoritmo de fijación | I-DT | Salvucci & Goldberg (2000) |
| `IDT_WINDOW_MS` / `IDT_DISPERSION_PX` | 300 ms / 60 px | Iniciales 150 ms / 30 px (pensados para mouse). Se ampliaron tras pruebas con el Tobii 5: leer implica saltos entre palabras y el sensor tiene ruido de decenas de px. *No calibrado formalmente.* |
| Entrega de muestras | push por WebSocket | El Tobii entrega ~90 Hz; el polling de 100 ms descartaba ~90 % de las muestras |
| Fijación IDT obligatoria | solo con mouse | Con mirada real basta quedarse 500 ms en el mismo elemento: leer produce dispersión alta aunque sí se esté leyendo |
| `ELEMENT_SWITCH_GRACE_MS` | 300 ms | Un cambio de elemento se confirma solo si dura; absorbe el ruido del sensor. *Diseño.* |
| `GAZE_SMOOTH_MS` / `EDGE_MARGIN_PX` (solo Tobii, 2026-10-20) | **100 ms** / 40 px | El punto del Tobii temblaba en los bordes del párrafo y el sistema creía que la persona se había ido. Se usa la **mediana de los últimos 150 ms** (no cada punto suelto) y un **margen de 40 px** alrededor del elemento actual (si el punto cae en espacio en blanco cerca del borde, sigue contando; si entra en otro elemento, cambia). Simulación (`node tests/test_estabilidad_mirada.js`, ruido σ 25 px, 34 Hz): salidas falsas **28.5 → 0.1 por minuto**; cambio real al párrafo vecino detectado a los 0.4 s (antes saltaba en falso 1.3 s antes). *Inicial*: confirmar con el Tobii real. **Ajuste con la sesión piloto real (P00, reproducida con distintos valores):** demora al cambiar de elemento 0.34 s (sin suavizar) · 0.41 s (150 ms) · **0.36 s (100 ms)**; rebotes por minuto 2.6 · 1.0 · **1.3** → se eligió 100 ms. El contorno que sigue la mirada ya no tiene animación (sumaba 0.2 s de retraso visual) y no se muestra en sesión. |
| `BLINK_GRACE_MS` | 450 ms | Un parpadeo normal dura ~100–400 ms. *Diseño.* |
| `TOOLTIP_HOLD_MS` | **4000 ms** (antes 2500) | El tooltip sigue visible tras desviar la mirada. **Piloto P01 (2026-10-20, Tobii):** 6 de 15 tooltips se ocultaban a los ~3 s con 0–0.7 s de mirada registrada dentro: el tooltip no tenía margen (con ~41 px de error la mirada caía justo afuera) y, si la mirada pasaba por otro elemento camino al tooltip, leerlo no detenía la cuenta. Arreglado: margen de 40 px también en el tooltip (Tobii), **mientras se mira el tooltip no se oculta**, y 4 s de permanencia al apartar la vista. `help_hidden` registra ahora `tooltip_rect`. Probado en el navegador (reloj controlado). |
| Mirada → página | **Automático** (2026-10-20) | Antes: píxeles de pantalla usados tal cual + `GAZE_OFFSET_Y` −40 px manual (el punto caía más abajo por las barras del navegador). Ahora el servidor envía la mirada como proporción de pantalla (0–1) y `frontend/js/gaze_mapping.js` la convierte según el equipo (resolución, escala de Windows, posición de la ventana y barras del navegador; con o sin F11). Lo que quede lo corrige la **comprobación de 5 puntos** al inicio de cada sesión (`calibracion.html`): una recta por eje, guardada por persona, y el error medido (`gaze_check`) para el criterio de exclusión (aceptable ≤ 60 px). Pruebas: `node tests/test_gaze_mapping.js` (PC con y sin F11, laptop al 125 %, ventana movida) y punta a punta con un Tobii simulado. **Falta probar con el Tobii real.** |

**Para probar sin código:** `GAZE_SOURCE=tobii python app.py` arranca en modo Tobii sin cambiar `GAZE_INPUT_SOURCE`.

**Puente automático (2026-10-20):** en modo Tobii, `app.py` abre `gaze_server.exe`
en otra ventana (antes había que abrirlo a mano), cierra puentes viejos de una
ejecución anterior y lo vuelve a abrir si se cae o se desconecta (acepta una sola
conexión). Además, la conexión ya no se corta si el Tobii deja de enviar unos
segundos (antes había un límite de 5 s al recibir). Probado con el Tobii real:
~34 muestras por segundo, todas válidas; al reiniciar `app.py` el puente se
renueva y los datos siguen llegando.

Trade-off explícito: más tolerancia al ruido y a parpadeos significa reaccionar
más lento a un cambio real de atención. El mapeo a píxeles asume navegador en
pantalla completa real (F11) en el monitor principal.

### 4. Modelos de IA

| Uso | Modelo (Ollama, local) | Parámetros | Origen del valor |
|---|---|---|---|
| Texto y tablas | `phi3` (MIT) | temperatura 0.1, ≤ 200 tokens, entrada ≤ 900 caracteres | 400 → 900 caracteres no cambió la velocidad medida (3.2 s vs 3.1 s) y evita cortar lo técnico al final de párrafos de ~450 caracteres |
| Ayuda ampliada (segundo nivel) | `phi3` | temperatura 0.1, ≤ 320 tokens, máx. 3 términos en el esquema (`maxItems`), mismo `num_ctx` (1024) que el nivel 1 | Medido: si `num_ctx` cambia entre peticiones, Ollama **recarga phi3 (~6 s)**; con 1536 la ampliada tardaba 8.9 s, con 1024 compartido 3.5 s. Peor caso: 735 tokens. Sin `maxItems` se cortaba el JSON (3/26 vacías) |
| Imágenes y gráficas | `qwen2.5vl:3b`, Q4_K_M (Apache 2.0) | temperatura 0, ≤ 120 tokens, imagen ≤ 512 px | Probar 720 px no mejoró la lectura de datos |

**Por qué Ollama (medido, RTX 3070 Ti de 8 GB):** Qwen en fp16 con Transformers
ocupa 7.5 GB; con phi3 cargado a la vez la VRAM no alcanzaba y cada análisis
tardaba **11–16 s**. Con Qwen cuantizado en Ollama conviven ambos modelos al 100 %
en GPU y cada análisis tarda **2.6–3.3 s**. Costo: menor fidelidad al leer valores
(ver limitaciones). Ambos modelos son gratuitos y funcionan sin internet tras la
descarga, sin límites de uso.

**Gráficas y tablas:** se probó que sin título, ejes, valores y leyenda de
columnas el modelo daba explicaciones genéricas (p. ej. una analogía de "recetas
de pastel" para una tabla de coeficientes); con ellos explica los valores reales.

### 5. Diseño de los estímulos (las tres páginas)

**Aspecto visual (2026-10-17):** cada página tiene un tema claro propio que
imita un tipo de sitio real: **fácil** = revista de divulgación (EcoPlaneta,
verde), **intermedio** = enciclopedia en línea (EcoWiki, estilo wiki) y
**avanzado** = revista científica (J. Clim. Res., estilo artículo académico).
Solo cambia el CSS (`frontend/css/temas.css`): el texto y la estructura HTML
son los mismos, porque el sistema identifica cada bloque por su posición.
En sesión se oculta la barra "Fácil / Intermedio / Avanzado", que revelaba el
nivel al participante. **Verificado:** las 18 preguntas de comprensión siguen
encontrando su bloque; el tooltip tapa contenido en 0/44 elementos (antes 3/44);
las 4 gráficas se siguen analizando bien con fondo claro (2.7–3.0 s).
Respaldo del diseño anterior y capturas: `respaldos/diseno_antes_2026-10-17/`
(solo local, no está en git; para volver atrás, ver su `LEEME.md`).

Mismo tema (cambio climático) en los tres niveles, para no confundir dificultad
con familiaridad del tema; cambian la estructura y la densidad:

- **Fácil** (`siteA.html`): divulgación; imagen grande, viñetas, cuadro comparativo,
  gráfica de 3 barras (hielo del Ártico en septiembre), viñetas de acciones y foto
  de paneles solares.
- **Intermedio** (`siteB.html`): estilo enciclopedia; texto, tabla de 3 columnas,
  gráfica de líneas, glosario, sección "El océano y el carbono" (2 párrafos,
  gráfica de CO₂ en Mauna Loa y foto de corales blanqueados).
- **Avanzado** (`siteC.html`): estilo artículo científico; resumen y metodología
  densos, tabla de coeficientes, gráfica de barras con valores, referencias,
  sección "Retroalimentaciones y forzamiento efectivo" (2 párrafos, gráfica de ERF
  por componente con valores negativos, foto de una charca de deshielo).

**Contenido agregado el 2026-10-05 (medido con INFLESZ antes de dejarlo):** cada
bloque nuevo cae en el nivel de su página. Fácil: 30 palabras → 84.9 y viñetas
72–81 (*Low*). Intermedio: 45.2 y 45.2 (*Medium*); hubo que reescribir dos
versiones, que daban 37.0 (*High*) y 57.0 (*Low*). Avanzado: 5.7 y 3.7 (*High*).
Las gráficas nuevas llevan `data-design-level` (Low / Medium / High según la
página). Los datos son aproximados y así lo dicen sus pies de figura: hielo
ártico de septiembre (≈ NSIDC), CO₂ de Mauna Loa (≈ NOAA), ERF por componente
(≈ IPCC AR6). *Conviene verificar las cifras contra las fuentes antes del
experimento.* Fotos nuevas, todas de **dominio público** en Wikimedia Commons
(se descartó una de paneles con licencia CC BY porque exige un crédito visible,
que el sistema analizaría como texto): `Carver, Route 44 Solar Array` (paneles),
`Coral Bleaching in Hawaii.jpg`, `Summer Arctic Melt Pond-SHEBA.JPG`.

**Para no revelar el nivel:** se quitaron los subtítulos ("Artículo de nivel
intermedio · densidad media…", "Sección de nivel avanzado…") y el nivel del pie
de página. *Siguen revelándolo* la barra de navegación (Fácil / Intermedio /
Avanzado) y el título de la pestaña ("Nivel Avanzado · …").

### 6. Pendiente y alcance de lo documentado

- Los umbrales de dwell (2000 ms), tolerancias (450/300 ms, 60 px) y el offset
  son **iniciales**; no se han calibrado con participantes.
- No se ha medido aún el acuerdo entre el nivel del sistema y la dificultad
  *percibida*. Plan: puntuación 1–5 por bloque de cada participante y correlación
  (Spearman) con INFLESZ y con el nivel del modelo.
- No implementado: tiempo de lectura esperado según la longitud del bloque,
  rutina de calibración. (El registro de sesiones ya está; ver "Sesiones con
  participantes" y la sección 8.)

### 7. Registro de mejoras medidas (antes → después)

Cada fila es una mejora aplicada y su efecto medido, para poder graficarla.
Hardware: RTX 3070 Ti (8 GB), Ollama con `phi3` y `qwen2.5vl:3b`; fecha de las
mediciones: 2026-10-04. Los datos crudos están en `evaluation/results/`
(`history.csv`, `metrics_*.json` y `mediciones_historicas.csv`).

**Reproducible** con `python evaluation/run_metrics.py --suite all` (con Ollama
corriendo; cada ejecución agrega filas a `history.csv`, así se comparan versiones
futuras contra estas). La variante "antes" es una versión anterior del sistema
reconstruida en el script, sobre el mismo contenido real de las páginas.

| Mejora | Métrica | Antes | Después | n |
|---|---|---|---|---|
| Idioma por defecto: español si no hay evidencia (tablas de solo números caían a inglés) | Idioma detectado correctamente, tablas | 3/4 | **4/4** | 4 |
| | Idioma detectado correctamente, total | 10/11 | **11/11** | 11 |
| Mínimo de la legibilidad de 15 a 8 palabras | Bloques de la página **fácil** resueltos por fórmula (sin depender del modelo) | 3/9 | **9/9** | 9 |
| | ...de **intermedio** | 4/7 | **7/7** | 7 |
| | ...de **avanzado** | 4/9 | **9/9** | 9 |
| | Bloques de la página fácil que son *Low* y no llaman al modelo | 3/9 (33 %) | **8/9 (89 %)** | 9 |
| Prompt de texto: de analogía a "definir el término, sin recapitular" | Explicaciones que empiezan con "Imagina" | 17/18 (94 %) | **0/18** | 18 |
| | El término elegido aparece en el texto | 22 % | **100 %** | 18 |
| | Copia de frases del texto (trigramas) vs. versión "dos partes" | 8–12 % | **3 %** | 18 |
| | Longitud de la explicación (palabras, promedio) vs. "dos partes" | 37–43 | **21** | 18 |
| | Latencia por explicación de texto | 3.3 s | **2.6 s** | 18 |
| | JSON válido sin tener que rescatarlo (prompt original, sin formato) | 72 % | **100 %** | 18 |
| Prompt de visión: de inglés a español | Respuestas en español (Qwen) | 33 % | **100 %** | 9 |
| | Latencia por análisis de imagen | 2.8 s | **2.6 s** | 9 |
| | ⚠ Efecto secundario: nivel asignado a la gráfica de avanzado | Medium 3/3 | **Low 3/3** | 3 |
| Nivel diseñado de las gráficas (`data-design-level`) en vez del juicio del modelo *(2026-10-05)* | Gráfica de **avanzado** con el nivel diseñado (*High*) | 0/3 (modelo: Low 3/3, **sin ayuda**) | **3/3** | 3 |
| | Gráfica de **intermedio** con el nivel diseñado (*Medium*) | 3/3 | **3/3** | 3 |
| | Gráficas con explicación para mostrar | 6/6 | **6/6** | 6 |
| | Longitud de la explicación, palabras (intermedio / avanzado) | 19 / 23 | **19 / 24** | 3 |
| | Latencia por análisis de imagen (3 imágenes) | 2.6 s | **2.6 s** | 9 |
| | *Descartado:* prompt con "explicación obligatoria", longitud en intermedio | 19 | 46 (cortada por tokens) | 3 |
| Sin ayuda en títulos + término en el texto + subtítulos quitados *(2026-10-05; revisión con el sistema real en el navegador, mismos elementos de antes, corrida 1)* | Ayudas que se mostrarían | 26 | **17** | — |
| | Innecesarias (títulos, subtítulos, notas, referencias) | 10 | **4** (notas y 1 referencia) | — |
| | Incorrectas | 3 | **0** | — |
| | Correctas y útiles | 5 | **7** | — |
| Textos de la gráfica SVG al modelo de visión *(2026-10-05, `run_metrics --suite vision`)* | Gráfica de avanzado: la explicación menciona la unidad (CO₂ equivalente) | 0/3 | **3/3** | 3 |
| | Gráfica de intermedio: explica el patrón (no solo "la línea azul muestra…") | 0/3 | **3/3** (*juicio del revisor*) | 3 |
| | Gráfica de avanzado: orden de sectores invertido, en el navegador | 2/2 | **0/2** (ya no enumera el orden) | 2 |
| | ⚠ Nuevo error: dice "toneladas" cuando la unidad es *giga*toneladas | 0/3 | 3/3 | 3 |
| | Latencia por imagen | 2.6 s | **2.6 s** | 9 |
| Ayuda de tablas y gráficas: "qué quiere mostrar" en vez de "qué mide" / término *(2026-10-26; payloads exactos de `payloads_paginas.json` y, para las gráficas nuevas, el navegador con el backend real; juicio del revisor)* | Tablas: la ayuda dice qué muestra la tabla (no solo define un término) | 0/4 | **6/6** | 2 tablas |
| | Gráficas: la ayuda dice la conclusión correcta | 4/8 (avanzado: solo título y unidad) | **8/8** payloads + **10/10** navegador (sin la radial) | 4 + 5 gráficas |
| | ⚠ Tablas: largo de la ayuda (pide ≤ 35 palabras) | 20–35 | 35–50 (recortadas a 55) | 6 |
| | *Descartado:* pista "si hay valores negativos" (ERF: "los negativos indican disminución con el tiempo") y "si el eje muestra años" (ERF: frase rota) | — | — | 2 c/u |
| | Gráfica radial: título sin "1991–2024" (decía "aumenta con el tiempo") y mes antes de su valor en el SVG | 0/2 | **3/3** | 3 |
| | Latencia por gráfica / tabla | 2.7–4.4 s / 2.5–8 s | **2.5–3.3 s / 3.0–3.5 s** | — |
| Contexto de página al modelo: título (`h1`) + sección *(2026-10-06, `python evaluation/ab_contexto.py --reps 2`; 51 elementos, cada uno sin y con contexto seguidos)* | Ayudas que se mostrarían (corrida 1 / 2) | 26 / 26 | 25 / 24 | 51 |
| | Ayudas bloqueadas por término fuera del texto | 1 / 1 | **4 / 5** | 51 |
| | Ayudas cuyo término está en el título de la página | 0 / 1 | **3 / 4** | — |
| | Términos repetidos en la misma página | 1 / 1 | 1 / 1 | — |
| | Latencia (llamadas al modelo) | 2.85 s | 2.83 s | — |
| | *Juicio del revisor, cambios que se repiten en ambas corridas:* fotos de intermedio que reciben ayuda descriptiva | 0 | ⚠ 2 | 2 |
| | …párrafo de Limitaciones (High) que se queda sin ayuda (eligió el término del título, bloqueado) | no | ⚠ sí | 2 |
| | …Metodología: definición imprecisa de "modelo lineal generalizado" en vez de la correcta de "errores autocorrelacionados" | no | ⚠ sí | 2 |
| | …fácil, "Recuerda": aparece una ayuda trivial ("acción diaria") | no | ⚠ sí | 2 |
| | …Resumen de avanzado: define el término central (forzamiento radiativo neto / **ECS**) en vez de repetir "regresión multivariable" | no | ✓ sí | 2 |
| | …Retroalimentaciones: sin contexto define "amplificación ártica" con el albedo invertido (corrida 2); con contexto define ERF correctamente | ✗ | ✓ | 2 |

| Contexto, 3 variantes solo en texto y tablas *(2026-10-06, `ab_contexto.py --reps 2 --solo-texto --variantes sin seccion_texto titulo_seccion_texto`; 40 elementos)* | Ayudas (corrida 1 / 2): sin / solo sección / título + sección | 19 / 19 | **18 / 18** · 17 / 15 | 40 |
| | Bloqueadas por término fuera del texto | 1 / 1 | **2 / 2** · 4 / 5 | 40 |
| | Términos repetidos en la misma página | 1 / 1 | **0 / 0** · 0 / 0 | — |
| | *Juicio del revisor, cambios frente a "sin" (2 corridas):* mejoran / empeoran | — | **8 / 2** · — | — |
| | …párrafo High que se queda sin ayuda (Limitaciones) | no | **no** · ⚠ sí (2/2) | 2 |
| | Latencia | 2.75 s | 2.74 s · 2.76 s | — |
| Ayuda por conducta en texto (atascado / relectura, ritmo adaptativo) *(2026-10-11, `node tests/test_reading_model.js`: 35 párrafos reales × 6 perfiles de lector **simulados** × 20 semillas; escenario base / exigente)* | Ayuda innecesaria a quien entiende (rápido, promedio, lento) | 100 % (regla anterior) | **0 % / 0 %** | 20 × 3 |
| | Cobertura a quien se traba (rápido, promedio, lento) | 100 % | **94–100 % / 97–98 %** | 20 × 3 |
| | Demora desde que empieza el párrafo hasta la ayuda | ~3 s | ⚠ **21–36 s / 23–39 s** | — |
| | Misma regla con ritmo promedio fijo (sin adaptar): lector rápido que se traba, cobertura | — | 34 % / 49 % | 20 |
| | …lector lento que entiende, ayuda innecesaria | — | 7 % / ⚠ 72 % | 20 |
| | *Descartado:* atascado a más tardar en esperado + 8 s: demora | — | −1 a −2 s; +8–15 % de ayudas innecesarias (exigente) | — |
| Relectura **dentro** del párrafo + tope de atascado de 15 s *(2026-10-11; el usuario notó que la ayuda solo salía al salir y volver; `node tests/test_reading_model.js`, quien se traba alterna quedarse / releer volviendo / releer dentro; base / exigente)* | Cobertura a quien se traba | v1: 63–76 % / 88–96 % | **83–100 % / 91–98 %** | 20 × 3 |
| | Ayuda innecesaria a quien entiende (incluye "revisa un dato 1 s") | 0 % | **0 % / 0–1 %** | 20 × 4 |
| | Demora | 20–34 s / 22–39 s | 19–32 s / 21–36 s | — |
| | Umbral de relectura en el párrafo: 0.4 s → 1.5 s, ayuda innecesaria a quien revisa | 38 % | **0 %** (cobertura 95 → 90 %, +1.3 s) | 20 |
| | Tope de atascado +15 / +10 / +8 / +5 s: espera de quien solo se queda / ayuda innecesaria a lento (exigente) | — | 27 / 26 / 25 / 23 s · 1 / 10 / 15 / 24 % → **se dejó +15 s** | 20 |
| | Navegador real: lee "Causas" 13 s y vuelve al inicio sin salir | sin ayuda (antes había que salir y volver) | **ayuda a los 1.5 s** | 1 |
| | Navegador real: vuelve 1 s arriba a revisar un dato | — | **sin ayuda** | 1 |
| "Leído" al 40 % (antes 70 %) + relectura en el párrafo medida con fijaciones *(2026-10-11; el usuario sintió ~2.5 lecturas antes de la ayuda)* | Lector rápido sin ritmo adaptado: lecturas hasta la ayuda (simulación) | 1.39 | **1.18** | 20 |
| | …cobertura | 79 % | **86 %** | 20 |
| | Ayuda innecesaria a quien entiende (base / exigente) | 0 % / 0–12 % | **0 % / 0–12 %** (sin cambio) | 20 × 5 |
| | *Descartado:* bajar además los factores (1.15/1.3) / el umbral de atascado (1.3×): ayuda innecesaria en el exigente | — | 21–45 % / 53–75 % | 20 × 5 |
| | Navegador real: lector rápido, lee "Causas" una vez y vuelve al inicio | ~2.2 lecturas (calculado) | **1.17 lecturas** | 1 |
| | Métricas de fijación por visita registradas (cantidad, tiempo, media) | no | **sí** (`visitas.csv`) | 1 |
| Prueba de punta a punta en el navegador (mouse, reloj controlado, backend y registro reales) | Ritmo adaptado leyendo rápido 5 párrafos fáciles | 140 ms/sílaba | **91** | 1 |
| | "Recuerda" (Medium, esperado 3.3 s) con lector trabado: ayuda a los… | 2.0 s (regla anterior) | **4.9 s** (1.5 × esperado) | 1 |
| | "Causas" (Medium) leído con fluidez en 11 s: ¿ayuda? | sí, a los 2 s | **no** | 1 |
| Ritmo aprendido en **cualquier página y nivel** *(2026-10-25; el usuario: el sistema no debe depender de una página fácil ni de una calibración previa. `node tests/test_reading_model.js`, 20 semillas; base / exigente)* | Pilotos P00/P01/P03 reaplicados: veces que el ritmo aprendió | **0 / 0 / 0** (nivel solo con el análisis, y solo párrafos Low) | **4 / 7 / 2** | 3 |
| | Lector rápido que no pasa por la fácil: párrafos hasta su ritmo (±15 %) | 20 (la mitad nunca llega) | **4.4** | 20 |
| | Lector rápido que empieza en avanzado y se traba: cobertura | 84 % / 77 % | **94 % / 84 %** | 20 |
| | Lector lento que empieza en avanzado y entiende: ayuda innecesaria | 7 % / ⚠ 57 % | **0 % / ⚠ 33 %** | 20 |
| | Resto de perfiles (empiezan en fácil): innecesaria / cobertura | 0–1 % · 88–100 % / 0–12 % · 91–98 % | 0–1 % · 88–100 % / 0–4 % · 88–96 % | 20 × 8 |
| | ⚠ Costo (escenario exigente: los textos difíciles se leen más lento de lo que suponen los factores 1.3/1.6): el ritmo aprendido queda ~15 % más lento que el real y la cobertura baja 2 puntos en algunos perfiles | — | ritmo 162 vs 140 ms/síl (promedio) | 20 |
| | Navegador: sílabas y nivel disponibles al cargar la página, antes de cualquier análisis; ritmo aprendido en párrafos High/Medium y recuperado en la página siguiente | — | **sí** | 1 |
| Mínimo de sílabas para aprender el ritmo 20 → **40** *(2026-10-25; sesión real en la laptop: textos de 21–33 sílabas dieron 48–180 ms/síl y el ritmo cayó de 130 a 84 en la página fácil; simulación con 14 perfiles × 20 semillas, con un escenario de ruido fijo de entrada/salida de −1 a +1.5 s)* | Ruido tipo Tobii: error del ritmo final (promedio / peor caso) | 5.7 % / 19 % | **2.2 % / 5 %** | 20 × 14 |
| | Ruido tipo Tobii y escenario base: ayudas innecesarias / cobertura | 0.2 % / 94.5 % | **sin cambio** | 20 × 14 |
| | ⚠ Escenario exigente (factores de nivel subestiman la dificultad real): innecesaria en el peor perfil / cobertura promedio | 32 % / 90.8 % | 46 % / 88.9 % | 20 × 14 |
| | En la sesión real, las medidas de párrafos largos fueron parecidas entre niveles (Medium/High 86–117, Low 98–131): los factores parecen correctos (más cerca del escenario con ruido que del exigente; n = 1) | — | — | 1 |
| | …al volver tras 7 s fuera (relectura): ayuda a los… | 0.5 s | **0.6 s** | 1 |
| | Marcado → acierto / cobertura calculados en `paginas.csv` | — | funciona | 1 |
| Tooltip ubicado sin tapar contenido (`computeTooltipPlacement`: derecha, izquierda, debajo, arriba) *(2026-10-11)* | Elementos de las páginas cuyo tooltip tapa contenido | 45/51 | **16/51** | 51 |
| | Con el tooltip del nivel 2 (288 px de alto vs. 136 px), solo elementos que pueden recibir ayuda (ventana 1280×800) | — | **3/44** (los mismos 3 que con el nivel 1) | 44 |
| Fotos con nivel diseñado Low + notas al pie y referencias sin ayuda (`NO_HELP_SELECTOR`) *(2026-10-11)* | Fotos que pueden recibir ayuda | 6 (el modelo decidía) | **0** (por diseño) | 6 |
| | Notas al pie entre los párrafos Medium/High que pedían ayuda ampliada | 3/16 | **0** (no se analizan) | 16 |
| Segundo nivel: ayuda ampliada (`/expand`) *(2026-10-11, `python evaluation/medir_ayuda_ampliada.py --reps 2`; 13 párrafos con ayuda × 2; detalle en `evaluation/results/revision_ayuda_ampliada_20261011.md`)* | Respuestas válidas: antes / después de `maxItems: 3` en el esquema | 23/26 (3 vacías: JSON cortado por tokens) | **26/26** | 26 |
| | Latencia de la ampliada: `num_ctx` 1536 / 1024 compartido con el nivel 1 | 8.89 s (phi3 se recargaba ~6 s en cada cambio) | **3.47 s** (nivel 1 alternando: 2.95 s) | 26 |
| | Con 2 o más términos / solo la frase simple | 19 / 4 | **23 / 3** | 26 |
| | Repite el término del primer nivel | 0 | 0 | 26 |
| | Palabras por explicación (promedio) | 60.3 | 61.2 | 26 |
| | *Juicio del revisor:* correcta / imprecisa / incorrecta | — | **17 / 3 / 6** (avanzado: 7 / 2 / ⚠ 5 de 14) | 26 |
| | Error 500 en `/expand` con "CO₂" (el `print` fallaba si la consola no es UTF-8) | 1 de 13 párrafos | **0** | 32 |
| | Navegador real, "Causas" (esperado 18.0 s), sigue trabado tras la 1.ª ayuda (27.1 s): nivel 2 a los… | — | **40.7 s** acumulados (calculado 40.6), al instante y sin tapar el párrafo | 1 |
| | Navegador real, "El océano absorbe…": relee dentro → 1.ª ayuda; lo relee completo a ritmo normal → nivel 2 | — | ⚠ **sale durante la segunda lectura** (0.75 × esperado < 1 lectura en Medium) | 1 |
| Ayuda que reaparece tras una salida corta *(2026-10-11, navegador real, reloj controlado)* | Mouse: sale 2 s a otro párrafo y vuelve | sin tooltip | **reaparece** la misma ayuda (`help_reshown`, mismo `help_id`) | 1 |
| | Sale 7 s y vuelve (relectura) | — | **segundo nivel** a los 0.1 s; la primera no reaparece | 1 |
| | Tobii: sale 1 s (menos que los 2.5 s de espera) / 3 s y vuelve | — | sigue visible sin registro nuevo / reaparece (`help_reshown`) | 1 |
| | `level2_extra_fraction` 0.75 → **1.0**: relectura completa a ritmo normal tras la 1.ª ayuda (prueba `node tests/test_reading_model.js`) | nivel 2 a los 16.3 s de 16.8 s | **sin nivel 2** | 1 |
| Elección del término: 3 candidatos + filtros (símbolos, ya explicados en la página) + el de más sílabas *(2026-10-11, `python evaluation/ab_terminos.py --reps 2`; 13 párrafos en orden × 2; criterio fijado antes; detalle en `evaluation/results/revision_terminos_20261011.md`)* | Párrafos con ayuda | 24/26 | **26/26** | 26 |
| | Términos repetidos en la misma página | 4 | **0** | 26 |
| | *Juicio:* término relevante (el más difícil o central) | 14/22 | **16/22** | 22 |
| | *Juicio:* definiciones incorrectas / imprecisas | 0 / 2 | **0** / 3 | 26 |
| | Latencia del primer nivel | 2.82 s | 3.61 s | 26 |
| | *Descartado:* candidatos en el orden del modelo (sin sílabas): incorrectas | 0 | ⚠ 2 | 26 |
| | Resumen de avanzado: define la sensibilidad climática de equilibrio (término central) | 0/2 | **2/2** | 2 |
| | ⚠ Forzamiento radiativo efectivo: elige un término secundario ("amplificadores térmicos") | 0/2 | 2/2 | 2 |
| | Segundo nivel con la misma elección: incorrectas en **avanzado** | 5/14 | **2/14** | 14 |
| | …correctas / imprecisas / incorrectas (total) | 17 / 3 / 6 | ⚠ 13 / 9 / 4 | 26 |
| | …con 2 o más términos | 23 | ⚠ 12 (se descartan los ya explicados) | 26 |

Lectura de la ayuda por conducta: en la simulación deja de dar ayuda a quien no
la necesita (antes 100 %) manteniendo casi toda la cobertura, y el ritmo
adaptativo es lo que la sostiene con lectores rápidos y lentos. **Costo:** la
ayuda llega más tarde (hay que esperar al menos el tiempo de lectura de la
persona para saber que se trabó). **Límite:** los lectores son simulados y se
traban de forma clara; con personas, el piloto (marcado → acierto y cobertura)
dirá cuánto de esto se sostiene. Hallazgo de la prueba en el navegador: el
tooltip de un párrafo puede tapar el inicio del siguiente y, mientras está
visible, la mirada ahí cuenta como "leyendo el tooltip" (resuelto el
2026-10-11 con la ubicación del tooltip: 45/51 → 16/51 elementos tapados).

Lectura de la ayuda ampliada: al medirla aparecieron tres fallas que no se
veían con el código solo (error 500 por un carácter, JSON cortado, recarga del
modelo) y se arreglaron. Queda bien en fácil e intermedio, pero **en avanzado
5 de 14 explicaciones tienen un error** (sensibilidad climática definida en
círculo, "CO₂: un gas que quema y quema"), y se repiten en ambas corridas: es
el límite conocido de phi3 con términos muy técnicos. **Decidido
(2026-10-11):** `level2_extra_fraction` de 0.75 a **1.0**: con 0.75, en
párrafos Medium una sola relectura completa a ritmo normal tras la primera
ayuda ya daba el nivel 2. **Costo:** quien de verdad sigue trabado lo recibe
0.25 × esperado más tarde (~4–5 s en un párrafo Medium típico). El segundo
nivel **se mantiene en avanzado**: por nivel de dificultad, sus explicaciones
incorrectas no son más frecuentes en High que en Medium (2/14 vs. 2/12); lo
que tiene más son explicaciones vagas (6/14 vs. 3/12).

Lectura de la elección del término: en el primer nivel mejora sin costo en
corrección (más términos centrales, ninguno repetido, ningún párrafo sin
ayuda; +0.8 s que no se notan porque la ayuda llega ≥ 20 s después del
análisis). En el segundo nivel arregla los errores que venían **del término**
(avanzado 5 → 2 incorrectas: desaparecen "CO₂ quema y quema" y la
sensibilidad climática en círculo), pero la calidad general **no mejora**
(correctas 17 → 13, imprecisas 3 → 9; corridas distintas, comparación
indicativa): lo que queda son definiciones y resúmenes imprecisos de phi3,
un límite del modelo que la elección del término no resuelve.

Con "solo sección" mejoran (en ambas corridas): el Resumen define el término
central (forzamiento radiativo neto) en vez de repetir "regresión multivariable";
"Retroalimentaciones" deja de definir la amplificación ártica con el albedo al
revés; la nota al pie y la definición repetida de "acidificación" quedan
bloqueadas. Empeora: en fácil aparece una ayuda trivial ("acción diaria") en
"Recuerda" (frase en el borde de Medium, INFLESZ 49.5). **Se adoptó "solo
sección, solo texto".**

Lectura de la primera medición del contexto (título + sección en todo): **resultado mixto**. El contexto acerca al
modelo a los términos centrales del artículo (bueno en el Resumen de avanzado),
pero también lo **jala hacia los términos del título** aunque no estén en el
párrafo (el bloqueo `concept_in_text` los frena, y por eso esos párrafos se quedan
sin ayuda), vuelve "elegibles" fotos que antes eran Low y hace más descriptivas
las explicaciones de las gráficas. Una corrida anterior el mismo día
(`contexto_20261006_183946_INVALIDA_gpu_ocupada.json`) **no es válida**: otro
programa usaba la GPU y el modelo de visión excedía el tiempo límite.

Notas de lectura: (1) en las filas de texto, "antes" para la copia y la longitud
es la versión "dos partes" (la inmediatamente anterior); la versión de analogía
copia solo 2 % porque inventa en vez de repetir (ver el resto de métricas).
(2) Las longitudes de variantes anteriores están ya recortadas a 55 palabras.
(3) Todas las variantes de texto dieron 0/18 explicaciones vacías con `format: "json"`
y con esquema.
(4) Desde el 2026-10-05 la variante de visión "es_prompt_con_pie_actual" se
llama `es_prompt_con_pie` (ya no es la actual); la actual es
`es_con_pie_nivel_diseno_actual`. La suite agrega por gráfica: nivel final vs.
diseñado, si hay explicación, longitud y lo que dijo el modelo.
(5) **Reproducibilidad del juicio del modelo (medido):** con temperatura 0 y el
mismo prompt sin pie, la gráfica de avanzado dio *Low* 3/3 el 2026-10-04 y
*Medium* 3/3 el 2026-10-05. Las 3 repeticiones de una corrida coinciden, pero
entre días no; por eso el nivel de las gráficas no se deja al modelo.

**Mediciones puntuales del desarrollo** (no se pueden re-ejecutar con el script;
en `mediciones_historicas.csv`):

| Mejora | Métrica | Antes | Después | n |
|---|---|---|---|---|
| Qwen de Transformers fp16 a Ollama Q4 | Latencia por análisis de imagen, con phi3 a la vez | 11.2–16.1 s | **2.6–3.3 s** | 5 / 4 |
| | VRAM de Qwen | 7.54 GB | **2.8 GB** | 1 |
| Tiempo límite de generación sin contar la carga del modelo | Primera petición con modelos descargados | error a los 37.6 s | **5.5 s** | 1 |
| "El último gana" (cola de una inferencia a la vez) | Peticiones obsoletas descartadas al llegar 3 seguidas | sin mecanismo: las 3 se procesaban *(por diseño, no medido)* | **2 de 3** (en 0.4–2.1 s) | 2 |
| Límite de entrada de texto de 400 a 900 caracteres | Respuestas con mensaje genérico (prompt de analogía) | 1/6 | **0/6** | 6 |
| Esquema JSON estricto | Explicaciones vacías con `format: "json"` y otro prompt | 7/12 | **0/12** | 12 |
| Tope de palabras en el prompt | Longitud real que produce phi3 al pedirle 40 / 30 palabras | 50 / 62 (prom.) | sin efecto: se recorta en código a 55 | 7 |

Ideas de gráficas: barras agrupadas antes/después por mejora; latencia de visión
por configuración (fp16 sola, fp16 con phi3, Q4); proporción de respuestas en
español y de "Imagina" por versión de prompt.

### 8. Plan de evaluación: ¿el sistema ayuda?

Estado de cada punto: **definido** (decidido e implementado), **propuesto**
(criterio razonable, a confirmar con la asesora) o **pendiente** (falta crearlo).

**Diseño (definido): intra-sujeto, 3 condiciones.** Cada participante lee las
tres páginas **una vez**, cada una con una condición distinta: sin ayuda,
automática o a pedido. Los 6 órdenes posibles se **contrabalancean** entre
participantes (el índice sugiere el patrón según el número: P01 → 1, P07 → 1
otra vez). Con participantes en **múltiplos de 6**, cada página tiene cada
condición el mismo número de veces, así que la dificultad de la página no se
confunde con la condición. Nota: la página fácil casi no tiene ayuda (1
párrafo Medium), así que su condición casi no se nota. En "sin ayuda" el sistema analiza igual y registra la ayuda que habría
dado (comparación sobre los mismos elementos).

**Orden de las páginas (propuesto):** fijo, fácil → intermedio → avanzado.
Amenaza: las tres tratan el mismo tema, así que lo aprendido en una ayuda en la
siguiente (y el cansancio recae en avanzado). Como la condición sí se
contrabalancea, ese efecto se reparte entre ambas condiciones, pero no
desaparece. Alternativa: rotar el orden, con el costo de que leer avanzado
primero puede desanimar.

**Qué se mide y de dónde sale:**

| Pregunta | Medida | Fuente | Estado |
|---|---|---|---|
| **¿Se entiende mejor con ayuda?** (pregunta principal) | Puntaje en una prueba de comprensión por página (6 preguntas: 3 literales y 3 inferenciales, ligadas a su bloque) | Cuestionario tras cada página, antes del marcado | **Borrador** con fundamento y referencias verificadas: [`evaluation/prueba_comprension.md`](evaluation/prueba_comprension.md); falta revisión de la asesora y validación |
| ¿Se percibe más fácil? | Dificultad percibida 1–5 por página (y por bloque, para la validez del nivel) | Cuestionario | **Pendiente** |
| ¿Cambia la lectura? | Relecturas en elementos elegibles para ayuda; dwell medio en elegibles; tiempo en la página | `paginas.csv`, `visitas.csv` | **Definido** (ya se registra) |
| **¿La ayuda llega a quien la necesita?** | Al terminar cada página el participante marca lo que le costó (`marking.js`): **acierto** = de los elementos con ayuda, % marcados; **cobertura** = de los marcados, % con ayuda. En "sin ayuda" cuenta la ayuda suprimida | `paginas.csv` | **Definido** (2026-10-11) |
| ¿Se usa la ayuda? | % de ayudas *leídas* (≥ 500 ms con la mirada dentro del tooltip), tiempo visible | `ayudas.csv` | **Definido**; el umbral de 500 ms es criterio inicial. Solo tiene sentido con el Tobii (con mouse hay que mover el cursor al tooltip) |
| ¿La ayuda es correcta? | Calificación de cada ayuda mostrada: correcta / imprecisa / incorrecta; acuerdo entre dos calificadores (kappa de Cohen) | Columna `calificacion` de `ayudas.csv` | **Propuesto** |
| ¿Molesta o sirve? | Utilidad e intrusividad percibidas (Likert 1–5) | Cuestionario final | **Pendiente** |
| ¿El nivel del sistema coincide con la dificultad percibida? | Correlación de Spearman entre dificultad percibida por bloque e INFLESZ / nivel del sistema | Cuestionario + `visitas.csv` | **Propuesto** (ya estaba en la sección 6) |

**Importante:** el registro solo dice *cómo* se leyó. Para afirmar que el sistema
**ayuda** hace falta la prueba de comprensión; sin ella, una ayuda podría cambiar
la lectura (por ejemplo, menos relecturas) sin mejorar la comprensión.

**Cómo se compara (propuesto):**
- **Unidad de análisis:** participante × página (`paginas.csv`).
- **Análisis principal:** modelo lineal mixto
  `medida ~ condición + página + (1 | participante)`. *Condición* es el efecto
  que interesa; *página* absorbe que avanzado es más difícil que fácil; el
  efecto aleatorio absorbe que cada persona lee distinto. Para la dificultad
  percibida (ordinal 1–5), la versión ordinal del modelo.
- **Comprobación simple:** por participante, diferencia "con ayuda − sin ayuda"
  de la medida estandarizada por página (z dentro de cada página, para que fácil
  y avanzado sean comparables) y prueba de rangos con signo de Wilcoxon.
- **Sobre los mismos elementos:** relecturas y dwell en cada elemento elegible,
  con ayuda (`mostrada`) frente a sin ayuda (`suprimida`), entre participantes.
- Reportar **tamaños de efecto con intervalos de confianza**, no solo valores p.
- **Muestra:** con 6–12 participantes la potencia estadística es baja; los
  resultados se presentan como **estudio exploratorio**. Si un efecto no sale
  significativo, no prueba que el sistema no ayude.

**Usos adicionales de la mirada cruda (definido que se guarda; análisis propuesto):**
- *Sensibilidad de umbrales:* recalcular con `gaze.csv` + `layout` cuántas ayudas
  se habrían disparado con dwell de 1000 / 2000 / 3000 ms para Medium, y
  justificar (o ajustar) el 2000 ms con datos reales.
- *Calidad del seguimiento:* % de muestras inválidas por sesión
  (`muestras_invalidas_pct`); definir antes un criterio de exclusión (por ejemplo,
  > 30 % inválidas) para no decidirlo a la vista de los resultados.

**Falta decidir con la asesora:** número de participantes (múltiplo de 6), orden
de las páginas, tiempo por página (libre o fijo), contenido de la prueba de
comprensión y de los cuestionarios, y el criterio de exclusión.

### Referencias

*(Verificar los datos bibliográficos contra las fuentes originales antes de citarlas en la tesis.)*

- Barrio-Cantalejo, I. M., et al. (2008). Validación de la Escala INFLESZ para
  evaluar la legibilidad de los textos dirigidos a pacientes. *Anales del Sistema
  Sanitario de Navarra, 31*(2), 135–152.
- Rayner, K. (1998). Eye movements in reading and information processing: 20
  years of research. *Psychological Bulletin, 124*(3), 372–422.
- Salvucci, D. D., & Goldberg, J. H. (2000). Identifying fixations and saccades
  in eye-tracking protocols. *Proceedings of ETRA 2000*, 71–78.
- Szigriszt Pazos, F. (1993). *Sistemas predictivos de legibilidad del mensaje
  escrito: fórmula de perspicuidad* (tesis doctoral). Universidad Complutense de Madrid.
