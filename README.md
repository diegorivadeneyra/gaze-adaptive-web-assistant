# gaze-adaptive-web-assistant

Sistema de asistencia web adaptativa basada en la atención visual del usuario.

## Instalación (otra computadora)

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

## Fuente de coordenadas (mouse / Tobii 5)

Se elige en `backend/app.py` con `GAZE_INPUT_SOURCE` (`INPUT_SOURCE_MOUSE` o
`INPUT_SOURCE_TOBII`). Para usar el Tobii 5, ver `tobii_bridge/README.md`.
Con `?debug=0` en la URL se oculta el panel de monitoreo (para las sesiones con
participantes, de modo que no sesgue su atención).

---

## Criterios para la experimentación

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
  - Limitación conocida: phi3 a veces define mal un término técnico (en pruebas
    anteriores dijo que la sensibilidad climática es "la temperatura máxima que
    el clima puede alcanzar") y puede escribir con erratas. Es un límite del
    tamaño del modelo, no del prompt; uno mayor no cabe junto a Qwen en 8 GB de
    VRAM.

### 3. Captura de la mirada

| Parámetro | Valor | Criterio |
|---|---|---|
| Algoritmo de fijación | I-DT | Salvucci & Goldberg (2000) |
| `IDT_WINDOW_MS` / `IDT_DISPERSION_PX` | 300 ms / 60 px | Iniciales 150 ms / 30 px (pensados para mouse). Se ampliaron tras pruebas con el Tobii 5: leer implica saltos entre palabras y el sensor tiene ruido de decenas de px. *No calibrado formalmente.* |
| Entrega de muestras | push por WebSocket | El Tobii entrega ~90 Hz; el polling de 100 ms descartaba ~90 % de las muestras |
| Fijación IDT obligatoria | solo con mouse | Con mirada real basta quedarse 500 ms en el mismo elemento: leer produce dispersión alta aunque sí se esté leyendo |
| `ELEMENT_SWITCH_GRACE_MS` | 300 ms | Un cambio de elemento se confirma solo si dura; absorbe el ruido del sensor. *Diseño.* |
| `BLINK_GRACE_MS` | 450 ms | Un parpadeo normal dura ~100–400 ms. *Diseño.* |
| `TOOLTIP_HOLD_MS` | 2500 ms | El tooltip sigue visible tras desviar la mirada, para poder terminar de leerlo. Ajustado por comentarios en pruebas piloto. |
| `GAZE_OFFSET_Y` | −40 px | Corrección manual **provisional**: el punto detectado quedaba más abajo de lo real. Pendiente una rutina de calibración. |

Trade-off explícito: más tolerancia al ruido y a parpadeos significa reaccionar
más lento a un cambio real de atención. El mapeo a píxeles asume navegador en
pantalla completa real (F11) en el monitor principal.

### 4. Modelos de IA

| Uso | Modelo (Ollama, local) | Parámetros | Origen del valor |
|---|---|---|---|
| Texto y tablas | `phi3` (MIT) | temperatura 0.1, ≤ 200 tokens, entrada ≤ 900 caracteres | 400 → 900 caracteres no cambió la velocidad medida (3.2 s vs 3.1 s) y evita cortar lo técnico al final de párrafos de ~450 caracteres |
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

Mismo tema (cambio climático) en los tres niveles, para no confundir dificultad
con familiaridad del tema; cambian la estructura y la densidad:

- **Fácil** (`facil.html`): divulgación; imagen grande, viñetas, cuadro comparativo.
- **Intermedio** (`intermedio.html`): estilo enciclopedia; texto, tabla de 3 columnas,
  gráfica de líneas, glosario.
- **Avanzado** (`avanzado.html`): estilo artículo científico; resumen y metodología
  densos, tabla de coeficientes, gráfica de barras con valores, referencias.

### 6. Pendiente y alcance de lo documentado

- Los umbrales de dwell (2000 ms), tolerancias (450/300 ms, 60 px) y el offset
  son **iniciales**; no se han calibrado con participantes.
- No se ha medido aún el acuerdo entre el nivel del sistema y la dificultad
  *percibida*. Plan: puntuación 1–5 por bloque de cada participante y correlación
  (Spearman) con INFLESZ y con el nivel del modelo.
- No implementado: tiempo de lectura esperado según la longitud del bloque,
  persistencia/registro de datos de sesión, rutina de calibración.

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
