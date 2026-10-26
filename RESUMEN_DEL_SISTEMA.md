# Resumen del sistema (por componente, con pruebas)

Una página por componente: **qué es, para qué se usa en el sistema, con qué
valor y qué lo respalda**. Valores tomados del código el 2026-10-11.

Origen de cada valor:
- **Estándar:** publicado en la literatura.
- **Medido:** probado en este proyecto, con el script o archivo indicado.
- **Inicial:** criterio de diseño, todavía sin calibrar con personas.

Detalle de cada regla: [`REGLAS_DEL_SISTEMA.md`](REGLAS_DEL_SISTEMA.md).
Todas las mediciones antes → después: README, sección 7.

---

## El flujo en una línea

**Tobii 5 → punto de mirada → elemento que se mira → ¿qué tan difícil es?
→ ¿la persona se trabó? → ayuda (tooltip) → si se vuelve a trabar,
explicación ampliada → todo queda registrado.**

---

## 1. Captura de la mirada

| Qué | Valor | Origen / prueba |
|---|---|---|
| Dispositivo | Tobii Eye Tracker 5: **~34 muestras por segundo recibidas** (medido el 2026-10-20 con el Tobii real; antes se había anotado ~90) | Medido. La frecuencia oficial no se pudo verificar en la web |
| Camino del dato | SDK en C++ (`tobii_bridge/gaze_server.cpp`) → socket TCP → `backend/app.py` → WebSocket (puerto 5600) → navegador | Probado con mirada real (oct. 2026) |
| Entrega | Cada punto llega al instante por WebSocket | **Medido:** con consulta cada 100 ms se perdía ~90 % de las muestras |
| Mirada → página | Automático: proporción de pantalla → página según el equipo (`gaze_mapping.js`) + comprobación de 5 puntos por persona (`calibracion.html`) | Reemplaza el −40 px manual (2026-10-20). Probado con pruebas automáticas y un Tobii simulado; **falta el Tobii real** |
| Fuente activa hoy | **Mouse** (`GAZE_INPUT_SOURCE` en `app.py`). Para las sesiones hay que cambiarla a Tobii | — |

## 2. Fijaciones: algoritmo I-DT

**Qué es:** el I-DT (Salvucci y Goldberg, 2000) decide si la mirada está
*quieta*. Hay fijación cuando los puntos de los últimos 300 ms caben en 60 px.

| Para qué se usa en el sistema | Valor | Origen |
|---|---|---|
| **Con mouse:** exigir una fijación para empezar a contar la atención (que pasar el cursor por encima no cuente) | 300 ms / 60 px | **Inicial** (se pensó en 150 ms / 30 px y se amplió tras probar el Tobii: el sensor tiene ruido de decenas de px) |
| **Relectura dentro del párrafo:** solo cuenta el tiempo **con fijación** en el primer tercio (una regresión real, no un paso de la mirada) | ≥ 1.5 s | **Inicial / diseño** (`reread_requires_fixation`) |
| **Registro por visita:** cantidad de fijaciones, tiempo total en fijación y duración media | — | Se guarda en `visitas.csv` para validar el I-DT con el Tobii en el piloto |

Con mirada real **no** se exige fijación para empezar a contar: al leer, la
mirada salta entre palabras aunque sí se esté leyendo.

## 3. Dwell time (tiempo de permanencia)

**Qué es:** cuánto tiempo seguido está la mirada sobre el **mismo elemento**
(párrafo, tabla, gráfica). Se usa en **cuatro** lugares:

| Para qué | Valor | Origen |
|---|---|---|
| **Analizar** el elemento con la IA | 0.5 s seguidos | **Estándar aproximado:** ≈ 2 fijaciones de lectura de 200–250 ms (Rayner, 1998). Distingue atención de mirada de paso |
| **Tablas, gráficas e imágenes:** cuándo mostrar la ayuda | Medium 2 s · High 0.5 s · relectura 0.5 s | **Inicial** |
| **Texto:** tiempo **acumulado** en el párrafo, comparado con lo que *esa persona* debería tardar (un dwell relativo; ver §5) | 1.5 × esperado | **Inicial**, probado en simulación |
| **¿Leyó el tooltip?** | ≥ 0.5 s con la mirada dentro | **Inicial**; se calcula en `analyze_sessions.py` |

Tolerancias para que el ruido del sensor no corte el dwell:

| Tolerancia | Valor | Origen |
|---|---|---|
| Cambio de elemento: solo se confirma si dura | 300 ms | Diseño |
| Parpadeo: se ignora una pérdida de la mirada | 450 ms | Un parpadeo dura ~100–400 ms |
| El tooltip sigue visible tras mirar a otro lado | 2.5 s | Ajustado en pruebas piloto |

## 4. Dificultad del contenido (Low / Medium / High)

| Contenido | Cómo se decide | Origen / prueba |
|---|---|---|
| Texto de 8 palabras o más | Legibilidad **INFLESZ**: ≥ 55 Low, 40–55 Medium, < 40 High | **Estándar** (cortes). **Medido:** con mínimo de 8 palabras, 25/25 bloques se resuelven por fórmula (antes 11/25) |
| Gráficas y fotos | Nivel con que se diseñó el estímulo (`data-design-level`) | **Medido:** el juicio de la IA sobre la misma gráfica cambiaba de un día a otro (Low → Medium) |
| Tablas y textos cortos | Juicio de la IA | No calibrado |
| Títulos y notas al pie | Sin ayuda | **Medido:** eran 6 de 26 y 4 de 17 ayudas innecesarias |

Low nunca muestra ayuda (sí registra si la conducta la habría pedido).

## 5. Cuándo se muestra la ayuda: conducta de lectura

**Tiempo esperado del párrafo = sílabas × ritmo de la persona × factor del
nivel** (Low 1.0 · Medium 1.3 · High 1.6).

| Señal | Regla | Origen |
|---|---|---|
| **Atascado** | Lleva ≥ 1.5 × su tiempo esperado (a más tardar esperado + 15 s) | **Inicial** |
| **Relectura al volver** | Vuelve al párrafo después de haberlo leído y de estar fuera > 5 s | **Estándar** (las regresiones indican dificultad; Rayner, 1998) |
| **Relectura en el párrafo** | Ya lo leyó y vuelve al primer tercio con fijaciones ≥ 1.5 s | Igual; con 0.4 s daba ayuda a quien solo revisaba un dato |
| "Lo leyó" | Llega al último tercio con ≥ 40 % del tiempo esperado | **Inicial** |
| Salida corta con ayuda ya dada | Si sale < 5 s y vuelve, la misma ayuda reaparece (misma lectura) | Diseño; probado en el navegador |
| **Ritmo de la persona** | Arranca en 140 ms/sílaba y se adapta en cualquier página con párrafos de cualquier nivel (mediana de las últimas 5 lecturas normalizadas por nivel, solo párrafos de ≥ 40 sílabas; subir ≤ 10 % por lectura; límites 0.6–1.8 ×; sílabas y nivel calculados en el navegador) | **Estándar como referencia:** 278 palabras/min en español (Brysbaert, 2019) ≈ 108 ms/sílaba, así que 140 es conservador |

**Prueba (simulación, `node tests/test_reading_model.js`, 17 pruebas OK):**
35 párrafos reales × lectores **simulados** × 20 semillas.

| | Regla anterior (solo dificultad + tiempo fijo) | Regla por conducta |
|---|---|---|
| Ayuda innecesaria (a quien entiende) | 100 % | **0 %** (escenario exigente: 0–12 %) |
| Cobertura (a quien se traba) | 100 % | **83–100 %** |
| Demora de la ayuda | ~3 s | ⚠ 19–36 s (no se sabe que alguien se trabó antes de su tiempo de lectura) |

**Prueba en el navegador** (backend real, reloj controlado): leer un párrafo
con fluidez no da ayuda; quedarse trabado la da a 1.5 × el tiempo esperado;
volver al inicio del párrafo la da a los ~1.5–2.4 s.

## 6. Segundo nivel: explicación ampliada

| Qué | Valor | Origen / prueba |
|---|---|---|
| Cuándo | Tras la primera ayuda, se vuelve a trabar: **1.0 × esperado más**, o relee otra vez | **Inicial.** Con 0.75, una sola relectura a ritmo normal ya lo daba (prueba en el navegador) |
| Qué muestra | 2–3 términos del párrafo + "En pocas palabras" (la idea en palabras simples) | Diseño |
| Disponibilidad | Se pide en segundo plano: aparece al instante | **Medido** en el navegador |

## 7. Modelos de IA (locales, gratuitos, en Ollama)

Hardware: RTX 3070 Ti de 8 GB. Ambos modelos caben juntos en la GPU.

| Modelo | Para qué | Memoria de video | Latencia promedio (medida) |
|---|---|---|---|
| **phi3** (3.8B) | Texto y tablas: **primera ayuda** (definir el término) | 2.4 GB | **3.6 s** (`ab_terminos.py`, n = 26) |
| **phi3** | **Explicación ampliada** (segundo nivel) | (el mismo) | **3.5 s** (`medir_ayuda_ampliada.py`, n = 26) |
| **qwen2.5vl:3b** (Q4) | Gráficas e imágenes | 2.6 GB | **2.6 s** por imagen (`run_metrics.py`, n = 9) |

La latencia casi no se nota: el análisis empieza a los 0.5 s de mirar y la
ayuda por conducta llega 20 s o más después.

**Por qué Ollama (medido):** Qwen sin cuantizar ocupaba 7.5 GB y tardaba
11–16 s junto con phi3; cuantizado en Ollama, 2.6–3.3 s.

**Cómo se elige el término (medido, `ab_terminos.py`):** phi3 propone 3 y el
código elige. Descarta los que no están en el texto, los símbolos ("CO₂") y
los ya explicados en la página, y prefiere la palabra con más sílabas.

| | Antes | Ahora |
|---|---|---|
| Párrafos con ayuda | 24/26 | **26/26** |
| Términos repetidos en la página | 4 | **0** |
| Término central elegido (juicio) | 14/22 | **16/22** |

**Calidad revisada a mano (un revisor):**
- **Primera ayuda:** 0 de 26 definiciones incorrectas.
- **Explicación ampliada:** 13 correctas, 9 imprecisas y 4 incorrectas de 26.
- ⚠ **Límite del modelo**, sobre todo con términos muy técnicos; un modelo
  mayor no cabe en 8 GB.

## 8. Tooltip

| Qué | Valor | Prueba |
|---|---|---|
| Ubicación | Derecha, izquierda, debajo o arriba: la primera que no tape contenido | **Medido:** elementos tapados 45/51 → 16/51; con el tooltip alto del segundo nivel, 3/44 |

## 9. Registro y evaluación

| Qué | Dónde |
|---|---|
| Cada sesión: mirada cruda, visitas, fijaciones, ayudas mostradas o suprimidas, marcado de lo difícil | `data/sessions/` → `python evaluation/analyze_sessions.py` |
| Diseño (2026-10-20): dos métodos (automática y a pedido) alternados entre páginas; **orden de páginas aleatorio** por participante | `index.html` + `session.js` + `marking.js` |
| Cuestionarios, todos al final: comprensión por recuerdo libre (un recuadro por página), un NASA-TLX (Anexo 3, ponderado), SUS y post-experimento (Anexo 4) | `evaluation/cuestionarios_participante.xlsx` → `puntuar_cuestionarios.py` |
| "A pedido": botón "Ver ayuda" al estar lista; lo pedido se compara con lo que la regla habría detectado | `gaze.js` (`offerHelpButton`), `paginas.csv` |
| Acierto (la ayuda fue a algo que costó) y cobertura (lo que costó recibió ayuda) | `paginas.csv` |
| Prueba de comprensión (medida principal) | **Borrador:** `evaluation/prueba_comprension.md` |

---

## Qué está probado y qué no

| Probado | Aún no |
|---|---|
| El flujo completo funciona (navegador, backend y modelos reales) | **Nada se ha probado todavía con participantes** |
| Las reglas de conducta, con lectores **simulados** | Que la ayuda **mejore la comprensión** (necesita la prueba de comprensión y el estudio) |
| Latencias, uso de memoria y calidad de las ayudas (juicio de un revisor) | Calificación de las ayudas por **dos** personas (acuerdo kappa) |
| La integración del Tobii, con mirada real | **Calibración** del Tobii y validación del I-DT al leer con él |
| | Los valores **iniciales** (140 ms/sílaba, 1.5 ×, factores por nivel): se calibran en el piloto |

### Referencias citadas
- Brysbaert, M. (2019). How many words do we read per minute? *Journal of
  Memory and Language, 109*, 104047.
- Rayner, K. (1998). Eye movements in reading and information processing:
  20 years of research. *Psychological Bulletin, 124*(3), 372–422.
- Salvucci, D. D., & Goldberg, J. H. (2000). Identifying fixations and
  saccades in eye-tracking protocols. *Proceedings of the 2000 Symposium on
  Eye Tracking Research & Applications (ETRA)*, 71–78. ACM.
  (Verificada en la web el 2026-10-11.)
