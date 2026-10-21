# Revisión de la ayuda ampliada (segundo nivel) — 2026-10-11

Medición: `python evaluation/medir_ayuda_ampliada.py --reps 2` (un solo
`python app.py`, GPU libre: 537 MiB usados, 0 %). Para cada párrafo de texto
Medium/High de las tres páginas se pide la primera ayuda (`/analyze`) y luego
la ampliada (`/expand`), como hace el navegador.

- Corrida **antes** de los arreglos: `ayuda_ampliada_20261011_214958.json`
- Corrida **después**: `ayuda_ampliada_20261011_215735.json`

16 párrafos × 2 repeticiones = 32 respuestas. **3 de los 16 son notas al pie**
(`.footnote`) que en el navegador nunca reciben ayuda (`NO_HELP_SELECTOR`), así
que el análisis válido es **13 párrafos × 2 = 26**.

## 1. Problemas encontrados al medir y arreglados

| Problema | Causa | Arreglo | Efecto medido |
|---|---|---|---|
| `/expand` respondía **500** en un párrafo con "CO₂" | El `print` del registro en `app.py` fallaba con `UnicodeEncodeError` cuando la salida de la consola no es UTF-8 (redirigida en Windows = cp1252). Afectaba también a `/analyze` | `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")` al arrancar `app.py` | El script abortaba en el párrafo 13 → 32/32 respuestas |
| Ayuda ampliada **vacía** sin error (3 de 26) | phi3 enumeraba 4–5 términos largos, se acababan los 320 tokens (`done_reason: length`) y el JSON quedaba cortado; el rescate devolvía un objeto parcial | `maxItems: 3` en el esquema JSON (el código ya usaba 3 como máximo) y, si falta `terms` y `simple`, se devuelve error (el navegador registra `help_level2_unavailable`) | Caso cortado: 1/2 → 0/2 cortes (prueba directa). Válidas: 23/26 → **26/26** |
| Latencia de la ampliada **8.9 s** (nivel 1: ~2.6 s) | El nivel 1 usa `num_ctx` 1024 y el 2 usaba 1536: **Ollama recarga phi3 cada vez que cambia** (medido: `load_duration` 6.03 s en cada cambio, 0.01 s sin cambio) | Constante compartida `TEXT_NUM_CTX = 1024` (`text_analyzer.py`). Peor caso medido: 735 tokens (prompt + respuesta) | Ampliada **8.89 → 3.47 s**; nivel 1 alternando con la ampliada: 2.95 s |

Sin el arreglo de `num_ctx`, en el navegador la descarga anticipada de la
ampliada habría hecho que el **siguiente análisis de nivel 1** también
esperara la recarga (~6 s más).

## 2. Métricas automáticas (26 respuestas válidas para el análisis)

| Métrica | Antes | Después |
|---|---|---|
| Respuestas válidas | 23/26 | **26/26** |
| Con 2 o más términos | 19 | **23** |
| Solo la frase simple (0 términos) | 4 | 3 |
| Repite el término del nivel 1 | 0 | 0 |
| Términos descartados por no estar en el texto (de 32) | 2 | 4 |
| Frase simple cortada en 40 palabras ("…") | 3 | 2 |
| Palabras por explicación (promedio) | 60.3 | 61.2 |
| Latencia de la ampliada | 8.89 s | **3.47 s** |

## 3. Juicio del revisor (corrida "después", 26 respuestas)

Criterio: **correcta** = todo lo que dice es correcto y está de acuerdo con el
texto; **imprecisa** = idea correcta con un detalle inexacto o erratas;
**incorrecta** = al menos una afirmación falsa o sin sentido.

| Página | n | Correcta | Imprecisa | Incorrecta |
|---|---|---|---|---|
| Fácil | 2 | 2 | 0 | 0 |
| Intermedio | 10 | 8 | 1 | 1 |
| Avanzado | 14 | 7 | 2 | **5** |
| **Total** | 26 | **17 (65 %)** | 3 (12 %) | **6 (23 %)** |

Incorrectas:
- Intermedio, "La acidificación dificulta…" (rep. 1): "microalgas que los corales **consumen**" (viven en simbiosis con el coral y le dan alimento; no se las come).
- Avanzado, Resumen (2/2): define la sensibilidad climática de equilibrio de forma circular ("cuando el calentamiento es igual al calentamiento…"); en la rep. 2 la frase simple dice además que el planeta "emite más calor infrarrojo que recibe del sol".
- Avanzado, Forzamiento radiativo efectivo (2/2): "CO₂: un gas que **quema y quema**…"; en la rep. 1 la frase simple repite esa definición y queda cortada.
- Avanzado, pie de la Fig. 1 (rep. 2): "incluyendo los que reducen el impacto ambiental" (inventado: los 5 sectores son emisiones positivas).

Imprecisas: ENOS "en el sur / sudeste del Pacífico" (es el Pacífico
ecuatorial; 2/2) y, en "gases de efecto invernadero", "Química: CH4… se libera
de la tierra y del agua" con la errata "quemir" (también apareció en la
prueba del navegador).

**Lectura:** en fácil e intermedio la ayuda ampliada es casi siempre correcta;
en avanzado, 5 de 14 tienen un error. Coincide con la limitación conocida de
phi3 con términos muy técnicos (ya definía mal la sensibilidad climática en el
nivel 1). Los errores se repiten en ambas repeticiones del mismo párrafo
(Resumen y ERF), así que dependen del párrafo más que del azar. No se cambió el
prompt (elegir mejor el término y probar otros modelos quedan para después,
por decisión del usuario).

## 4. Prueba en el navegador (intermedio, reloj controlado, mouse)

Ventana emulada de 1280×3100, temporizadores propios detenidos y reloj
controlado (cada tick = 100 ms), backend y modelo reales.

| Escenario | Resultado |
|---|---|
| "Causas" (Medium, esperado 18.0 s): se queda trabado | Nivel 1 "atascado" a los **27.1 s** (1.5 × esperado) |
| …sigue trabado después de la ayuda | Nivel 2 "atascado" a los **40.7 s** acumulados (27.1 + 0.75 × 18.0 = 40.6 esperado), **al instante** (ya estaba descargado). Tooltip 📘 a la izquierda (x 47–347), sin tapar el párrafo (x 361–589) |
| "El océano absorbe…" (Medium, esperado 16.2 s): lo lee en ~13 s y vuelve al inicio | Nivel 1 "relectura en el párrafo" tras 2.4 s en el inicio |
| …lo vuelve a leer completo a ritmo normal (~13 s) | ⚠ Nivel 2 "atascado" **durante esa segunda lectura** (28.5 s = 16.3 + 0.75 × 16.2), antes de volver al inicio |

⚠ Hallazgo: con `level2_extra_fraction` = 0.75, en un párrafo Medium **una sola
relectura completa a ritmo normal** después de la primera ayuda ya da el
nivel 2 (leer a ritmo normal toma 1/1.3 ≈ 0.77 del tiempo esperado). En High
(1/1.6 ≈ 0.63) no pasa. Releer tras recibir una definición puede ser
normal (integrarla), así que podría ser ayuda innecesaria. **Decidido:** se
subió a 1.0 (con 0.75 el nivel 2 salía a los 16.3 s de una relectura de
16.8 s; con 1.0, no sale). Prueba agregada en `tests/test_reading_model.js`.

## 5. Tooltip del nivel 2 (más alto) y contenido tapado

Mismo algoritmo (`computeTooltipPlacement`), ventana de 1280×800, sobre los
elementos que pueden recibir ayuda (44 en las tres páginas: fácil 18,
intermedio 14, avanzado 12):

| Tooltip | Alto | Elementos donde tapa contenido |
|---|---|---|
| Nivel 1 (definición) | 136 px | 3/44 (fácil 1, intermedio 2) |
| Nivel 2 (ampliada) | 288 px | 3/44 (los mismos) |

## 6. Después: mejor elección del término

Con la nueva elección del término (mismo día) la ampliada se volvió a medir:
avanzado pasa de 5 a 2 incorrectas, pero en total quedan 13 correctas, 9
imprecisas y 4 incorrectas. Ver `revision_terminos_20261011.md` §3.
