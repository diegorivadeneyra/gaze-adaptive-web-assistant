# Revisión de las ayudas generadas (2026-10-05)

**Cómo se obtuvo.** Con el sistema real (`python app.py`, phi3 + qwen2.5vl:3b en
Ollama) se pidió la ayuda de **cada elemento analizable** de las tres páginas,
usando el mismo código del navegador (`extractContent`, rasterizado de gráficas,
`/analyze`, nivel diseñado de las gráficas). 2 corridas por elemento, 42 elementos.
"Elegible" = el sistema mostraría ayuda (nivel Medium o High).

**Qué es medido y qué es juicio.** Los niveles, los conceptos y los textos son
salida real del sistema. La **clasificación** (útil, innecesaria, incorrecta…) es
el juicio de un solo revisor (Claude), no una medición: conviene que la revise
otra persona antes de usarla como dato (ver README §8, kappa de Cohen).

## Resumen (corrida 1; 26 ayudas elegibles)

| Clase | n | % |
|---|---|---|
| A. Correcta y útil | 5 | 19 % |
| B. Correcta, pero no define lo más difícil del texto (o repite un término ya definido) | 4 | 15 % |
| C. Imprecisa | 2 | 8 % |
| D. Innecesaria: títulos, subtítulos, notas, referencias | 10 | 38 % |
| E. Incorrecta | 3 | 12 % |
| F. Solo describe la imagen o la gráfica, no explica nada | 2 | 8 % |

Elegibles por página: fácil 3 de 11 · intermedio 12 de 16 · avanzado 11 de 15.

**Variabilidad entre las 2 corridas (medida):** el nivel cambió en 1 de 42 elementos
(título de fácil: Medium → Low, así que la ayuda aparece en una corrida y en la
otra no). El concepto elegido fue el mismo en 42 de 42. El texto cambió de
redacción en la mayoría, y en 1 caso cambió de correcto a incorrecto
("Consecuencias regionales").

## Detalle (corrida 1)

| Página | Elemento | Nivel (fuente) | Concepto definido | Clase | Observación |
|---|---|---|---|---|---|
| Fácil | Título h1 | Medium (modelo) | derretimiento del hielo | D | Ayuda en un título; en la corrida 2 salió Low |
| Fácil | Foto del glaciar | Medium (modelo) | Comparación de imágenes | F | Describe la foto (1909 vs 2004), no agrega comprensión |
| Fácil | "Pequeñas acciones diarias…" | Medium (INFLESZ 49.5, en el borde) | acumulación de energía | **E** | Término **inventado**, no aparece en el texto; "acumulación de energía" significa otra cosa (almacenar energía) |
| Intermedio | Título h1 | Medium (modelo) | evidencia observacional | D | Correcta, pero en un título |
| Intermedio | Subtítulo "Artículo de nivel intermedio · densidad…" | High (INFLESZ 35.3) | densidad media de información | D | Metatexto; además **le dice al participante el nivel de la página** |
| Intermedio | Párrafo "Causas" | Medium (INFLESZ 44.7) | gases de efecto invernadero | B | Correcta, pero el término difícil es **forzamiento radiativo** y no se define |
| Intermedio | h3 "Evidencia observacional" | Medium (modelo) | evidencia observacional | **E** | Dice "sin intervención de instrumentos", y el párrafo de abajo habla de estaciones, boyas y satélites |
| Intermedio | Párrafo de registros | High (INFLESZ 9.6) | emisiones industriales | B | Correcta, término poco relevante |
| Intermedio | h3 "Consecuencias regionales" | Medium (modelo) | consecuencias regionales | D | Genérica; en la corrida 2, incorrecta ("más allá de sus fronteras") |
| Intermedio | Párrafo de consecuencias | Medium (INFLESZ 52.0) | capas de hielo | C | "Sumideros de agua" es impreciso |
| Intermedio | "Notas: los valores son promedios…" | High (INFLESZ 30.9) | valores promedios globales | D | Nota al pie |
| Intermedio | Gráfica de temperatura | Medium (diseño) | Variación de temperatura global | F | Describe la línea; no explica qué es "variación respecto a 1900" (anomalía) |
| Intermedio | "Notas de imagen: fotografía de archivo…" | High (INFLESZ 26.1) | fotografía de archivo | D | Nota al pie |
| Intermedio | "Efecto invernadero" (Ver también) | Medium (modelo) | efecto invernadero | A | Correcta (≈55 palabras, en el límite) |
| Intermedio | "Huella de carbono" (Ver también) | Medium (modelo) | Huella de carbono | A | Correcta |
| Avanzado | Título h1 | High (INFLESZ −11.9) | forzamiento radiativo antropogénico | C | "Cambio en la atmósfera" es vago; es un cambio en el balance de energía |
| Avanzado | Subtítulo "Sección de nivel avanzado · … IEEE/PubMed" | High (INFLESZ 28.6) | estilo IEEE/PubMed | D | Metatexto; revela el nivel |
| Avanzado | Resumen | High (INFLESZ 18.0) | regresión multivariable | B | Correcta, pero **ECS** (sensibilidad climática de equilibrio), el concepto central, nunca se define en ninguna ayuda |
| Avanzado | Metodología | High (INFLESZ 39.2) | errores autocorrelacionados | A | Correcta; quedan sin explicar heterocedasticidad, Newey-West, AIC y R² |
| Avanzado | Gráfica de barras | High (diseño; el modelo dijo Low) | Energía como principal emisor | **E** | **Orden equivocado**: dice "seguido por el transporte y la industria", pero industria (10.4) > transporte (8.2) |
| Avanzado | Pie de la Fig. 1 | Medium (INFLESZ 53.9) | GEI equivalentes | A | Correcta y útil (explica CO₂-eq) |
| Avanzado | Tabla de coeficientes | Medium (modelo) | regresión multivariable | B | Repite el término del Resumen; no ayuda a leer β, EE, p e IC |
| Avanzado | h2 "Resultados y discusión" | Medium (modelo) | Resultados y discusión | D | Título de sección |
| Avanzado | Resultados | High (INFLESZ 26.1) | forzamiento por aerosoles antropogénicos | A | Correcta; quedan ECS y "enmascaramiento" |
| Avanzado | "Notas de imagen: fotografía histórica…" | High (INFLESZ 23.4) | fotografía histórica | D | Nota al pie |
| Avanzado | Referencia NOAA | Medium (modelo) | Global Surface Temperature Anomalies | D | Ayuda sobre una referencia bibliográfica |

## Otros hallazgos de la revisión

- Intermedio tiene un **glosario oculto** (botón "Glosario") que ya define
  *forzamiento radiativo*, *anomalía* y *albedo*. Es una fuente de ayuda que
  existe en ambas condiciones; hay que decidir si se deja.
- Los subtítulos y el pie de página dicen "nivel intermedio / avanzado": el
  participante ve el nivel diseñado de la página.
- Las fotos de intermedio y avanzado salieron Low (sin ayuda), y la de fácil,
  Medium. Sigue pendiente decidir si las fotos llevan nivel diseñado.

---

# Después de los cambios (misma noche, mismo procedimiento)

Cambios: sin ayuda en títulos; ayuda bloqueada si el término no está en el texto;
subtítulos que revelaban el nivel quitados; textos de las gráficas SVG pasados al
modelo de visión; contenido nuevo en las tres páginas. 2 corridas, 51 elementos.

## Mismos elementos que antes (corrida 1)

| Clase | Antes | Después |
|---|---|---|
| A. Correcta y útil | 5 | **7** |
| B. Correcta, no define lo más difícil / repite | 4 | 4 |
| C. Imprecisa | 2 | 1 |
| D. Innecesaria | 10 | **4** |
| E. Incorrecta | 3 | **0** |
| F. Solo describe | 2 | 1 |
| **Total de ayudas** | 26 | **17** |

Qué cambió en cada caso:
- **Desaparecen** las ayudas de los títulos (3 h1, 2 h3, 1 h2) y de los 2 subtítulos.
- "Acumulación de energía" (fácil) queda **bloqueada** en las 2 corridas.
- Gráfica de intermedio: de "La línea azul muestra…" a "la temperatura… ha aumentado
  desde 1900, con un aumento más rápido en las décadas más recientes" (F → A).
- Gráfica de avanzado: ya no invierte el orden, pero ahora dice "toneladas de CO2
  equivalente" (son gigatoneladas) y el concepto trae una errata ("Emitencias") (E → C).
- Siguen: notas al pie (3) y la referencia NOAA (1); la foto de fácil (descriptiva);
  el término poco relevante en "Causas", registros, Resumen (ECS sigue sin definirse) y tabla.

## Contenido nuevo (corrida 1, 9 ayudas)

| Página | Elemento | Clase | Observación |
|---|---|---|---|
| Fácil | Gráfica del hielo ártico | — | Nivel diseñado Low: sin ayuda, como corresponde |
| Fácil | Foto de paneles solares | F | "Los paneles solares producen electricidad limpia en un campo…" |
| Intermedio | Océano, párrafo 1 | A | Acidificación oceánica, correcta |
| Intermedio | Océano, párrafo 2 | B | Vuelve a definir "acidificación" (repetida) |
| Intermedio | Gráfica de CO₂ | F | Describe; menciona ppm sin explicarlo |
| Intermedio | Foto de corales | — | Low (sin ayuda) |
| Avanzado | Retroalimentaciones | **E** | Corrida 1: "la reducción del hielo **aumenta** la reflectividad" (es al revés). Corrida 2: correcta |
| Avanzado | Limitaciones | B | Define "forzamientos por aerosoles"; lo difícil es "colinealidad" |
| Avanzado | Gráfica de ERF | C | Corrida 1 agrega una definición imprecisa de ERF; corrida 2 solo describe |
| Avanzado | Pie de la Fig. 3 | C | "cambio en la fuerza del efecto de la radiación del calor": vago |
| Avanzado | Foto de la charca de deshielo | F | Describe a los investigadores |

Además, en la corrida 2, Resultados definió "enmascaramiento negativo" diciendo que
los aerosoles incluyen "el asfalto" (incorrecto).

**Lectura:** los cambios eliminaron el ruido y los errores que se podían atacar con
reglas (títulos, términos inventados, orden de la gráfica). Lo que queda es límite
del modelo (phi3 se equivoca en definiciones densas, 1 de cada 2 corridas en el
párrafo nuevo) o pendiente de decidir: fotos (F), notas y referencias (D) y
elección del término (B, necesita los términos marcados por una persona).
