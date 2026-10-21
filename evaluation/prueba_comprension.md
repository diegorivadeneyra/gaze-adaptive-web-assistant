# Prueba de comprensión (borrador )

**Para qué sirve:** es la medida principal de la tesis. El registro de mirada dice
*cómo* se leyó; esta prueba dice si se **entendió mejor con ayuda que sin ella**.

Estado: **borrador** (2026-10-11). Antes de usarla con participantes hay que
revisarla con la asesora y hacer el control de "¿se responde sin leer?" (§5).

---

## 1. En qué se basa (fundamento)

| Idea | Fuente | Cómo se usa aquí |
|---|---|---|
| Comprender un texto produce dos niveles de representación: la **base del texto** (lo que dice explícitamente) y el **modelo de situación** (lo que se entiende al integrarlo con el conocimiento previo) | Kintsch (1988), modelo de construcción-integración | Dos tipos de pregunta: **literales** (base del texto) e **inferenciales** (modelo de situación). La ayuda (definir el término difícil) debería notarse sobre todo en las inferenciales |
| Se puede medir el aprendizaje desde un texto con **preguntas de opción múltiple**, y el **conocimiento previo** cambia cuánto se beneficia el lector | McNamara y Kintsch (1996) | Formato de opción múltiple y un breve cuestionario de conocimiento previo, para controlarlo en el análisis |
| Alternativa validada: **técnica de verificación de oraciones** (decir sí o no a oraciones originales, parafraseadas, con el significado cambiado o ajenas al texto) | Royer, Hastings y Hook (1979) | Formato alternativo si la asesora prefiere sí/no (§7) |
| Saber que habrá preguntas hace leer **más lento**; en general se lee más lento para recordar que para leer normalmente | Brysbaert (2019), revisión de Carver (1992) y de Kemper y Sumner (2001) | Las instrucciones deben ser **iguales en ambas condiciones**. El ritmo adaptativo del sistema absorbe parte de esa lentitud (§4) |
| Un criterio habitual de "leyó con comprensión" es acertar al menos el **70 %** de preguntas sí/no | Taylor (1965), citado en Brysbaert (2019) | Referencia para un posible criterio de exclusión (decidir con la asesora) |
| Las preguntas y los ítems de un experimento son una muestra, igual que los participantes: el análisis debe tratar a **ambos** como efectos aleatorios | Baayen, Davidson y Bates (2008) | Modelo mixto con participante e ítem (§6) |
| Antecedentes de sistemas que ayudan a leer usando la mirada | Hyrskykari (2006), iDict; Biedert, Buscher y Dengel (2010), Text 2.0 | Marco de trabajos relacionados (no definen el formato de la prueba) |

---

## 2. Diseño de la prueba

- **6 preguntas por página** (18 en total): **3 literales y 3 inferenciales**.
- **Opción múltiple** con 4 opciones y una sola correcta, más **"No lo sé"**
  (reduce las respuestas al azar).
- **Opciones sin pistas** (Haladyna, Downing y Rodriguez, 2002): de **largo
  parecido** (diferencia de 2 a 8 caracteres; la correcta es la más larga solo
  en 4 de 18, lo esperable por azar), **todas plausibles** (errores comunes o
  datos de la propia página que no responden la pregunta) y con la correcta
  **repartida** (a: 4, b: 5, c: 5, d: 4). Excepción: A3, cuyas opciones son
  nombres de variables. Donde un distractor es cierto en el mundo real pero no
  lo dice el texto, la pregunta dice "según el texto".
- **Cada pregunta está ligada a un bloque de la página.** La correspondencia
  con el identificador del bloque en el registro está aparte, en
  `evaluation/assets/prueba_comprension_bloques.json` (es para el análisis; no
  la ven ni la asesora ni los participantes). Así se puede comparar el acierto en preguntas cuyo bloque
  **recibió ayuda** con las que no.
- **Sobre todo de bloques Medium/High**, donde actúa la ayuda; fácil tiene
  pocos, así que sus preguntas sirven además como **control**.
- Se responde **sin volver al texto**: la página se oculta. Así se mide lo
  comprendido, no la habilidad de buscar.
- **Puntaje:** 1 si acierta; 0 si falla o elige "No lo sé".

---

## 3. Preguntas

Formato de cada pregunta: **tipo · bloque (nivel)**. La respuesta
correcta va marcada con ✓ (no se le muestra al participante).

### Página fácil

**F1** · literal · párrafo inicial (Low)
¿Por qué se reduce el hielo de los polos y de las montañas, según el texto?
- a) Se derrite más rápido de lo que se forma. ✓
- b) Cada año cae menos nieve sobre esas zonas.
- c) El viento lo arrastra lentamente hacia el mar.
- d) Las lluvias de verano lo van disolviendo.
- e) No lo sé.

**F2** · literal · gráfica (Low)
Según la gráfica, ¿cuánto hielo había en el Ártico en septiembre de 2020?
- a) Unos 7.7 millones de km².
- b) Unos 3.9 millones de km². ✓
- c) Unos 6.3 millones de km².
- d) Unos 1.2 millones de km².
- e) No lo sé.

**F3** · literal · viñeta (Low)
Según el texto, ¿qué pasa con el agua de los glaciares que se derriten?
- a) Se evapora y vuelve a caer como lluvia.
- b) Se filtra al suelo y forma ríos subterráneos.
- c) Se congela de nuevo durante el invierno.
- d) Llega al mar y lo hace subir poco a poco. ✓
- e) No lo sé.

**F4** · inferencial · dato curioso (Low)
Si un glaciar desaparece, ¿por qué es difícil recuperarlo?
- a) Porque solo puede formarse cerca de los polos.
- b) Porque el agua derretida ya no puede congelarse.
- c) Porque tarda miles de años en volver a formarse. ✓
- d) Porque las montañas pierden altura con el tiempo.
- e) No lo sé.

**F5** · inferencial · párrafo y gráfica (Low)
Comparando 1980 con 2020, el hielo del Ártico en septiembre…
- a) aumentó en una cuarta parte.
- b) se mantuvo prácticamente igual.
- c) se redujo más o menos a la mitad. ✓
- d) desapareció casi por completo.
- e) No lo sé.

**F6** · inferencial · "Recuerda" (**Medium**)
¿Qué idea transmite el texto sobre las acciones diarias, como ahorrar energía?
- a) Solo funcionan si las impulsa el gobierno.
- b) Tienen efecto cuando las hace mucha gente. ✓
- c) Ayudan poco frente a la contaminación industrial.
- d) Sirven sobre todo para ahorrar dinero en casa.
- e) No lo sé.

### Página intermedia

**I1** · literal · "Causas" (**Medium**)
Según el texto, ¿qué libera principalmente los gases de efecto invernadero?
- a) La quema de combustibles fósiles. ✓
- b) Las erupciones de los volcanes activos.
- c) La evaporación del agua de los océanos.
- d) El humo de los incendios forestales.
- e) No lo sé.

**I2** · inferencial · "Causas" (**Medium**, término: forzamiento radiativo)
Que estos gases "retengan calor y aumenten el forzamiento radiativo" significa que…
- a) la Tierra recibe más luz del Sol que antes.
- b) el planeta devuelve menos energía al espacio. ✓
- c) la capa de ozono deja pasar más radiación.
- d) la superficie refleja más radiación solar.
- e) No lo sé.

**I3** · literal · "Evidencia observacional" (**High**)
Según el texto, ¿de dónde vienen los registros que muestran el aumento de la temperatura?
- a) De modelos climáticos hechos por computadora.
- b) De muestras de hielo extraídas en la Antártida.
- c) De anillos de árboles y sedimentos marinos.
- d) De estaciones, boyas oceánicas y satélites. ✓
- e) No lo sé.

**I4** · inferencial · tabla y Fig. 1 (Low/Medium)
¿Qué muestran los datos sobre la velocidad del calentamiento?
- a) Que la temperatura subió al mismo ritmo todo el siglo.
- b) Que el aumento se aceleró en las décadas recientes. ✓
- c) Que el aumento fue mayor a comienzos del siglo XX.
- d) Que la temperatura dejó de subir después de 1990.
- e) No lo sé.

**I5** · literal · "El océano y el carbono" (**Medium**)
Según el texto, ¿por qué baja el pH del mar?
- a) Porque el agua más caliente se vuelve ácida.
- b) Porque el deshielo agrega agua dulce al mar.
- c) Porque el CO₂ disuelto forma ácido carbónico. ✓
- d) Porque aumenta la cantidad de sal disuelta.
- e) No lo sé.

**I6** · inferencial · "La acidificación…" (**Medium**)
Un caracol marino podría verse perjudicado por la acidificación porque…
- a) le costaría más formar y mantener su concha. ✓
- b) los corales blanqueados dejarían de protegerlo.
- c) el agua más ácida reduciría su oxígeno.
- d) el plancton del que se alimenta crecería más.
- e) No lo sé.

### Página avanzada

**A1** · literal · Resumen (**High**)
¿Qué estima principalmente el estudio?
- a) El aumento futuro del nivel del mar.
- b) Las emisiones de cada sector económico.
- c) La sensibilidad climática de equilibrio. ✓
- d) La concentración de CO₂ esperada en 2050.
- e) No lo sé.

**A2** · inferencial · Resultados (**High**, término: ECS)
Una sensibilidad climática de equilibrio de ≈ 3.0 °C significa que…
- a) la temperatura global ya subió 3 °C desde 1880.
- b) el modelo tiene un margen de error de 3 °C.
- c) la temperatura subirá 3 °C antes del año 2100.
- d) con el doble de CO₂, se calentaría unos 3 °C. ✓
- e) No lo sé.

**A3** · inferencial · Tabla 1 (Medium)
Según la tabla, ¿qué variable **no** tuvo un efecto estadísticamente significativo?
- a) CO₂-eq.
- b) Aerosoles.
- c) ENOS.
- d) Actividad solar. ✓
- e) No lo sé.

**A4** · inferencial · Resultados (**High**, término: enmascaramiento)
Que los aerosoles tengan un "efecto de enmascaramiento negativo" quiere decir que…
- a) aumentan el calentamiento causado por el CO₂.
- b) reducen parte del calentamiento de los gases. ✓
- c) impiden medir bien la temperatura global.
- d) no tienen un efecto apreciable en el clima.
- e) No lo sé.

**A5** · literal · Retroalimentaciones (**High**)
Según el texto, ¿qué refuerza el calentamiento en latitudes altas?
- a) El aumento de la actividad solar en verano.
- b) Las variaciones asociadas al fenómeno de El Niño.
- c) La pérdida de hielo marino, que reduce el albedo. ✓
- d) Las interacciones de los aerosoles con las nubes.
- e) No lo sé.

**A6** · literal · Limitaciones (**High**)
¿Cuál de estas es una limitación que reconoce el estudio?
- a) Supone que la respuesta es lineal al forzamiento. ✓
- b) Analiza un período de datos demasiado corto.
- c) Deja fuera el efecto del vapor de agua y las nubes.
- d) No incluye los aerosoles entre las variables.
- e) No lo sé.

**Resumen por página:** fácil 1 pregunta sobre bloque Medium (5 Low, de control);
intermedio 5 Medium/High; avanzado 6 Medium/High.

---

## 4. Procedimiento propuesto

1. **Antes de empezar** (una vez): 3 preguntas de conocimiento previo, 1 a 5
   ("¿Cuánto sabes sobre cambio climático / efecto invernadero / estadística?").
2. **Instrucción igual para todos:** "Lee cada página para entenderla; al
   final de cada una responderás unas preguntas". Como saber que habrá
   preguntas hace leer más lento (Brysbaert, 2019), la instrucción debe ser
   idéntica en ambas condiciones.
3. Por cada página: **leer → preguntas (página oculta) → marcar lo que costó**.
   Las preguntas van **antes** del marcado: el marcado vuelve a mostrar la
   página y permitiría releerla antes de responder.
4. Las preguntas no tienen límite de tiempo, pero el tiempo se registra.

## 5. Antes de usarla: validar las preguntas

- **¿Se responde sin leer?** Pasar la prueba a 3–5 personas **sin** mostrarles
  las páginas. Las preguntas que la mayoría acierte por conocimiento general
  (candidatas: F3, I1) se reescriben, porque no miden comprensión del texto.
- **¿Es demasiado fácil o difícil?** Con el piloto se revisa el porcentaje de
  acierto de cada pregunta. Las que todos aciertan o todos fallan no
  distinguen entre condiciones.
- Revisar con la asesora que cada respuesta correcta sea inequívoca **según el
  texto**.

## 6. Cómo se analiza

- **Principal:** regresión logística de efectos mixtos por pregunta:
  `acierto ~ condición + tipo_pregunta + página + (1 | participante) + (1 | ítem)`
  (Baayen et al., 2008). El conocimiento previo entra como covariable.
- **Hipótesis específica:** la ayuda mejora más las **inferenciales** que las
  literales (interacción condición × tipo), porque la ayuda define el término
  que hace falta para el modelo de situación (Kintsch, 1988).
- **Por bloque:** como cada pregunta está ligada a su bloque, se compara el
  acierto cuando ese bloque **mostró** ayuda frente a cuando la **suprimió**
  (condición "sin ayuda").
- Con 6–12 participantes, los resultados son **exploratorios**.

## 7. Alternativa: verificación de oraciones (Royer et al., 1979)

En vez de opción múltiple, oraciones a responder con sí/no: originales,
parafraseadas, con el significado cambiado y ajenas al texto. Es más rápida de
responder y más fácil de equilibrar, pero mide sobre todo la base del texto
(menos inferencias). Se puede preparar si la asesora la prefiere.

---

## Referencias (verificadas en la web el 2026-10-11)

- Baayen, R. H., Davidson, D. J., & Bates, D. M. (2008). Mixed-effects modeling
  with crossed random effects for subjects and items. *Journal of Memory and
  Language, 59*(4), 390–412.
- Biedert, R., Buscher, G., & Dengel, A. (2010). Text 2.0. En *CHI '10
  Extended Abstracts on Human Factors in Computing Systems*. ACM. (Páginas y
  DOI a completar desde la ficha de la ACM al citar.)
- Brysbaert, M. (2019). How many words do we read per minute? A review and
  meta-analysis of reading rate. *Journal of Memory and Language, 109*, 104047.
  https://doi.org/10.1016/j.jml.2019.104047
- Hyrskykari, A. (2006). *Eyes in attentive interfaces: Experiences from
  creating iDict, a gaze-aware reading aid* (tesis doctoral). Universidad de
  Tampere.
- Haladyna, T. M., Downing, S. M., & Rodriguez, M. C. (2002). A review of
  multiple-choice item-writing guidelines for classroom assessment. *Applied
  Measurement in Education, 15*(3), 309–333. (Páginas a confirmar al citar.)
- Kintsch, W. (1988). The role of knowledge in discourse comprehension: A
  construction-integration model. *Psychological Review, 95*(2), 163–182.
- McNamara, D. S., & Kintsch, W. (1996). Learning from texts: Effects of prior
  knowledge and text coherence. *Discourse Processes, 22*(3), 247–288.
- Rayner, K. (1998). Eye movements in reading and information processing: 20
  years of research. *Psychological Bulletin, 124*(3), 372–422.
- Royer, J. M., Hastings, C. N., & Hook, C. (1979). *A sentence verification
  technique for measuring reading comprehension* (Technical Report No. 137).
  Center for the Study of Reading, University of Illinois.
- Taylor, S. E. (1965), citado en Brysbaert (2019): criterio de ≥ 70 % de
  acierto en preguntas sí/no. Citar a través de Brysbaert, o consultar el
  original.

