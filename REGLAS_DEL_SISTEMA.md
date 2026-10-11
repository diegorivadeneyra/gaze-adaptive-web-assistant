# Reglas del sistema (referencia rápida)

Documento para responder "¿cómo decide el sistema…?" y "¿cómo se mide…?".
Cada regla dice **dónde está en el código** y **de dónde sale el valor**:
*estándar* (publicado), *medido* (en este proyecto) o *inicial* (criterio de
diseño, a calibrar con el piloto). El detalle y las mediciones completas están
en el README.

---

## 1. El flujo en una línea

**Mirada → atención a un elemento → nivel de dificultad del contenido → ¿la
persona muestra que lo necesita? → ayuda (tooltip) → todo queda registrado.**

---

## 2. ¿Cuándo se analiza un elemento?

| Regla | Valor | Origen | Código |
|---|---|---|---|
| Se analiza al mirar el mismo elemento de forma sostenida | 0.5 s | Inicial (≈ 2 fijaciones de lectura; Rayner, 1998) | `gaze.js` `DWELL_THRESHOLD_MS` |
| Los títulos (h1–h6) no se analizan ni reciben ayuda | — | Medido (6 de 26 ayudas eran sobre títulos) | `gaze.js` `extractContent` |

---

## 3. ¿Qué tan difícil es el contenido? (nivel Low / Medium / High)

| Contenido | Cómo se decide | Origen | Código |
|---|---|---|---|
| Texto de 8 palabras o más | Legibilidad INFLESZ: ≥ 55 Low, 40–55 Medium, < 40 High | Estándar (cortes) / medido (mínimo de 8 palabras) | `readability.py` |
| Gráficas de las páginas | Nivel con que se diseñaron (`data-design-level`) | Diseño del estímulo (el juicio de la IA cambiaba entre días) | HTML + `image_analyzer.py` |
| Tablas, fotos y textos cortos | Juicio de la IA | No calibrado | `text_analyzer.py`, `image_analyzer.py` |

---

## 4. ¿Cuándo se MUESTRA la ayuda? (la regla central)

Se separan dos decisiones:

1. **¿Hay ayuda disponible?** La decide el **contenido**: Low no tiene ayuda;
   Medium y High sí.
2. **¿Esta persona la necesita ahora?** La decide su **conducta de lectura**.

### 4.1 Texto corrido: regla por conducta

**Tiempo esperado del párrafo = sílabas × ritmo de la persona × factor del nivel.**

La ayuda aparece si se cumple **una** de estas señales:

- **Atascado:** lleva en el párrafo **≥ 1.5 ×** su tiempo esperado, y **a más
  tardar esperado + 15 s**.
- **Relectura al volver:** vuelve al párrafo **después de haberlo leído** y
  de haber estado fuera **más de 5 s**.
- **Relectura en el párrafo** (desde el 2026-10-11): ya lo leyó y, **sin
  salir**, la mirada vuelve al **primer tercio** del párrafo con
  **fijaciones** que suman **≥ 1.5 s**. Es una **regresión**, el indicador
  clásico de dificultad en eye tracking. Así se detecta a quien relee sin irse.

**"Lo leyó"** = la mirada está en el **último tercio** del párrafo cuando ya
acumuló **≥ 40 %** de su tiempo esperado (llegar al final hojeando no cuenta).

Cómo se cuenta el tiempo:

| Situación | Qué hace |
|---|---|
| Sale **menos de 5 s** y vuelve | Sigue sumando (misma lectura: ruido del Tobii o mirar una gráfica) |
| Sale **más de 5 s** sin haberlo leído | Se **reinicia** (solo había mirado el inicio) |
| Sale más de 5 s **habiéndolo leído** y vuelve | **Relectura** → ayuda |
| Mira el tooltip | No suma al tiempo del párrafo |

**Fijaciones (I-DT, 300 ms / 60 px):** sirven para medir la relectura en el
párrafo (arriba) y se registran por visita: cantidad, tiempo total en
fijación y duración media (`element_exit` → `visitas.csv`). Con los datos del
Tobii del piloto se verá (a) qué % de la lectura detecta el I-DT como fijación
(si es bajo, ajustar 300 ms / 60 px o desactivar el requisito) y (b) si las
fijaciones largas anticipan lo que la persona marca como difícil.
**Dwell time:** sigue usándose en tres lugares: 0.5 s para analizar, el tiempo
fijo de tablas, gráficas e imágenes, y el **tiempo acumulado del párrafo**
(un dwell relativo: comparado con lo que esa persona debería tardar).

**Ritmo de la persona (adaptativo, sin medición previa):**
- Arranca en el **promedio general**: ≈ 140 ms por sílaba (≈ 220 palabras/min
  en español; Brysbaert, 2019, *a verificar*; ~2 sílabas por palabra, *medido*
  en las páginas).
- Cada vez que lee un **párrafo fácil (Low) completo y sin señales**, el ritmo
  se acerca al suyo (30 % del camino). Solo cuenta si el tiempo observado está
  entre 0.4 y 2 veces el esperado (fuera de eso: hojeo o distracción).
- Queda entre 0.6 y 1.8 veces el promedio. Se conserva entre páginas de la
  misma visita y se borra al iniciar o finalizar una sesión.

**Nivel Low:** nunca muestra ayuda, pero si la conducta la habría pedido se
registra (`help_would_trigger_low`) para estudiarlo.

| Parámetro | Valor | Origen |
|---|---|---|
| Ritmo base | 140 ms/sílaba | Literatura (a verificar) + medido (sílabas/palabra) |
| Factor del nivel | Low 1.0 · Medium 1.3 · High 1.6 | Inicial |
| Umbral de atascado | 1.5 × esperado, a más tardar esperado + 15 s | Inicial (tope: ver sensibilidad en §8) |
| Relectura en el párrafo | ≥ 1.5 s en el primer tercio, después de haberlo leído | Inicial (con 0.4 s, quien solo revisa un dato recibía ayuda) |
| "Lo leyó" | en el último tercio con ≥ 40 % del esperado acumulado | Inicial (con 70 %, un lector rápido sin ritmo adaptado necesitaba ~2 lecturas) |
| Relectura en el párrafo: solo tiempo con fijación | sí (`reread_requires_fixation`) | Diseño (poner `False` si el piloto muestra pocas fijaciones al leer con el Tobii) |
| Salida que corta la lectura | > 5 s | Inicial |
| Adaptación del ritmo | peso 0.3; límites 0.6–1.8 × base | Inicial |

Todos están en **un solo lugar**: `backend/analyzers/decision_engine.py`
(`READING_POLICY`). El navegador los recibe de `/config`. La lógica está en
`frontend/js/reading_model.js` (módulo sin dependencias, con pruebas en
`tests/test_reading_model.js`).

*Por qué el tope es de 15 s y no menor:* acortarlo casi no adelanta la ayuda
(quien solo se queda trabado: 27 s con +15 s, 23 s con +5 s) y aumenta las
ayudas innecesarias a lectores lentos (1 % con +15 s; 10 %, 15 % y 24 % con +10,
+8 y +5 s). Para saber que alguien está trabado **solo por quedarse** hay que
esperar al menos su tiempo de lectura. La señal que adelanta la ayuda de verdad
es la **relectura en el párrafo**.

### 4.2 Tablas, gráficas e imágenes: tiempo fijo

"Sílabas" no tiene sentido ahí, así que se mantiene la regla anterior:
Medium tras **2 s**, High tras **0.5 s**, y **0.5 s** si es una relectura
(*inicial*). Código: `decision_engine.py` (`HELP_POLICY`).

---

## 5. ¿QUÉ ayuda se da?

| Regla | Detalle | Origen |
|---|---|---|
| Texto: define el término más difícil | "Término: definición", sin resumir el texto ni usar analogías; máximo 55 palabras (recorte en código) | Medido (versiones anteriores copiaban el texto o inventaban) |
| Bloqueo si el término no está en el texto | Si el término definido no aparece en el párrafo, no se muestra | Medido (evitó un término inventado; 11/11 casos bien) |
| Contexto de sección | Al texto y las tablas se les pasa el subtítulo de su sección (no el título de la página) | Medido (8 mejoras / 2 empeoramientos; el título empeoraba) |
| Gráficas SVG | Se pasan sus valores y etiquetas escritos; se pide explicar qué mide | Medido (corrigió el orden de las barras; ahora menciona la unidad) |
| Modelos | `phi3` (texto) y `qwen2.5vl:3b` (imágenes), locales en Ollama | Medido (latencia ~2.7 s; caben juntos en 8 GB) |

---

## 6. ¿Cómo se mide si el sistema le SIRVE al usuario?

**Diseño intra-sujeto:** cada persona lee las 3 páginas, unas **con ayuda** y
otras **sin ayuda**, con 6 patrones rotados entre participantes. En "sin ayuda"
el sistema funciona igual, pero no muestra el tooltip: registra la ayuda que
habría dado.

| Pregunta | Medida | Estado |
|---|---|---|
| **¿Entiende mejor?** (principal) | Prueba de comprensión por página | **Pendiente** |
| ¿Le parece más fácil? | Cuestionario 1–5 | Pendiente |
| **¿La ayuda llega a quien la necesita?** | El participante **marca lo que le costó** al terminar cada página → **acierto** (de las ayudas, cuántas fueron a algo que marcó) y **cobertura** (de lo que marcó, a cuánto llegó la ayuda) | **Listo** (`marking.js`, `analyze_sessions.py`) |
| ¿Lee distinto? | Relecturas, tiempo por párrafo, tiempo en la página | Listo (registro) |
| ¿Usa la ayuda? | Tiempo con la mirada dentro del tooltip (≥ 500 ms = leída) | Listo |
| ¿La ayuda es correcta? | Calificación a mano de cada ayuda (dos personas, kappa) | Columna lista; calificar |

Comparación estadística propuesta: modelo mixto
`medida ~ condición + página + (1 | participante)`, más una comprobación con
Wilcoxon. Se reportan tamaños de efecto. Muestra: múltiplos de 6; con 6–12
personas es un estudio exploratorio.

---

## 7. ¿Cómo se comparan las MEJORAS del sistema?

Receta A vs. B, siempre igual:

1. **Mismo material:** el contenido real de las páginas
   (`evaluation/assets/payloads_paginas.json`, `bloques_lectura.json`).
2. **Las dos versiones sobre cada elemento,** una tras otra y en orden
   alternado, con 2–3 repeticiones (la IA varía).
3. **Mismas métricas:** automáticas (ayudas, bloqueos, repeticiones, latencia,
   idioma) y juicio (correcta o útil).
4. **Criterio fijado ANTES de medir** (por ejemplo: "más mejoras que
   empeoramientos y ningún párrafo High sin ayuda").
5. **Se anota** en el README (§7) y en `evaluation/results/` (`history.csv`).

Cuidados: tarjeta gráfica libre (sin juegos), comparar en la misma sesión y
verificar que solo haya un `python app.py`.

| Script | Qué compara |
|---|---|
| `python evaluation/run_metrics.py --suite all` | Idioma, legibilidad, prompts de texto y de visión |
| `python evaluation/ab_contexto.py` | Variantes de contexto de página |
| `node tests/test_reading_model.js` | Reglas de la ayuda por conducta (pruebas + simulación) |
| `python evaluation/analyze_sessions.py` | Sesiones reales: lectura, ayudas, acierto y cobertura |

---

## 8. Resultado de la regla por conducta (simulación, 2026-10-11)

Con los 35 párrafos reales y **lectores simulados** (no personas). Quien se
traba alterna tres conductas: se queda, relee después de salir, o relee dentro
del párrafo. `node tests/test_reading_model.js` (escenario base / exigente):

| Regla | Ayuda innecesaria (a quien entiende, incluido quien revisa un dato) | Cobertura (a quien se traba) | Demora de la ayuda |
|---|---|---|---|
| Anterior: solo contenido + tiempo fijo | **100 %** | 100 % | ~3 s |
| Conducta v1 (sin tope, relectura solo al volver) | 0 % | 63–76 % / 88–96 % | 20–34 s / 22–39 s |
| **Conducta v2 (actual: + tope 15 s + relectura en el párrafo)** | **0 % / 0–1 %** | **83–100 % / 91–98 %** | 19–32 s / 21–36 s |

Versión anterior de la simulación (sin la conducta "relee dentro"): ritmo
promedio fijo 0–72 % de ayudas innecesarias y 34–100 % de cobertura; ritmo
adaptativo 0 % y 94–100 %. Es decir: el ritmo adaptativo es imprescindible.

**Ajuste de tiempos (2026-10-11, el usuario sintió que tardaba ~2.5 lecturas).**
Propuesta probada por partes antes de aplicarla:

| Variante | Ayuda innecesaria (base / exigente) | Lector rápido sin ritmo adaptado: cobertura · lecturas hasta la ayuda |
|---|---|---|
| Tiempos anteriores (leído 70 %) | 0 % / 0–12 % | 79 % · 1.39 |
| **Solo "leído" al 40 % (aplicada)** | **0 % / 0–12 %** | **86 % · 1.18** |
| + factores 1.15/1.3 | 0–9 % / **21–45 %** | 94 % · 1.18 |
| + atascado 1.3× | 3–27 % / **53–75 %** | 94 % · 1.17 |

(El 12 % del exigente es "hojea y luego lee" y ya existía con los tiempos
anteriores.) En el navegador real, un lector rápido con el ritmo sin adaptar
que lee "Causas" una vez y vuelve al inicio recibe la ayuda a las **1.17
lecturas** (antes ~2.2).

**Prueba en el navegador real (reloj controlado):** leer "Causas" de arriba
abajo en 13 s no da ayuda; al volver al inicio sin salir, la ayuda aparece a
los 1.5 s. Leer otro párrafo y volver 1 s arriba a revisar un dato no da ayuda.

**Lectura:** la regla deja de dar ayuda a quien no la necesita y la sigue
dando a quien se traba. El ritmo adaptativo es lo que la hace funcionar con
lectores rápidos y lentos. **Costo:** la ayuda llega más tarde, porque no se
puede saber que alguien está trabado antes de que pase su tiempo de lectura.
**Límite:** son lectores simulados que se traban de forma clara; con
personas reales, el piloto (marcado → acierto y cobertura) dirá cuánto de esto
se sostiene.
