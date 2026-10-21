# Elección del término a definir — 2026-10-11

Pedido del usuario: mejorar la elección de términos **sin cambiar de modelo**
(phi3) y ver si mejora la ayuda, sobre todo en avanzado.

## 1. Variantes (`evaluation/ab_terminos.py --reps 2`)

| Variante | Qué hace |
|---|---|
| **A · modelo** (anterior) | El modelo elige **un** término y lo define |
| **B · candidatos** | El modelo propone hasta **3** términos con su definición; el código descarta los que no están en el texto, los **símbolos o fórmulas** ("CO₂", "pH") y los **ya explicados en la misma página**; se queda con el primero del modelo |
| **C · sílabas** | Igual que B, pero elige el término con la **palabra de más sílabas** (misma idea que INFLESZ: más sílabas por palabra = más difícil) |

Material: los 13 párrafos de texto Medium/High que pueden recibir ayuda (sin
notas al pie), recorridos **en orden** por página, × 2 repeticiones; cada
variante lleva su propia lista de términos ya explicados. Variantes seguidas
sobre cada párrafo, rotando el orden. Detalle: `terminos_20261011_221938.json`.

**Criterio fijado antes de medir** para adoptar B o C: (1) más términos
relevantes que A; (2) no más definiciones incorrectas que A; (3) ningún
párrafo pierde la ayuda (salvo por término repetido); (4) latencia +2 s como
máximo (la ayuda por conducta aparece ≥ 20 s después del análisis, así que la
latencia casi no se nota).

## 2. Primer nivel: resultados

| Métrica | A · modelo | B · candidatos | C · sílabas |
|---|---|---|---|
| Párrafos con ayuda | 24/26 | 26/26 | **26/26** |
| Bloqueados (término fuera del texto) | 2 ("La acidificación…", 2/2) | 0 | 0 |
| Términos repetidos en la misma página | 4 | 0 | **0** |
| *Juicio:* término relevante (el más difícil o central; 22 juicios, sin "Recuerda" ni "registros", que no tienen un término claramente técnico) | 14 | 15 | **16** |
| *Juicio:* definición incorrecta | 0 | ⚠ **2** | **0** |
| *Juicio:* definición imprecisa | 2 | 5 | 3 |
| Latencia | 2.82 s | 3.63 s | **3.61 s** |

**C cumple los 4 criterios; B no** (2 definiciones incorrectas: "dióxido de
carbono: dos átomos de carbono y dos de oxígeno" y un "modelo lineal
generalizado" mal definido). **Se adoptó C** (`TERM_SELECTION = "silabas"`).

Cambios que explican la mejora de C:
- **Resumen (avanzado):** define la **sensibilidad climática de equilibrio**
  (el término central) en vez de "forzamiento radiativo neto", 2/2, con una
  definición correcta. Antes, el segundo nivel la definía en círculo.
- **"La acidificación dificulta…" (intermedio):** antes quedaba **sin ayuda**
  (2/2 bloqueada); ahora define "microalgas" (correcta) o "esqueletos y conchas".
- **Pie de la Fig. 3 y Limitaciones (avanzado):** dejan de repetir términos ya
  explicados en la página.

Empeora:
- **Forzamiento radiativo efectivo (avanzado):** C elige "amplificadores
  térmicos" (2/2) en vez del término central (ERF), porque "amplificadores"
  tiene más sílabas. La definición es correcta, pero el término es secundario.
- **Limitaciones:** ninguna variante elige "colinealidad" (el término más
  difícil); C define "serie de forzamiento por aerosoles" de forma imprecisa.

**Límite:** el juicio es de un solo revisor (Claude), con 2 repeticiones; las
diferencias son pequeñas (16 vs. 14 relevantes). La regla de "ya explicado"
compara palabras: considera repetido "antropogénico" si antes se definió
"forzamiento por aerosoles antropogénicos".

## 3. Segundo nivel con la misma elección

`expanded_help.py` usa la misma función (`choose_terms`, modo sílabas) y el
navegador le envía los términos ya explicados en la página.
`python evaluation/medir_ayuda_ampliada.py --reps 2` (ahora en orden y con
esa lista). Comparado con la corrida anterior del mismo día:

| Métrica | Antes | Después |
|---|---|---|
| Válidas | 26/26 | 26/26 |
| Con 2 o más términos | 23 | ⚠ **12** (se descartan los ya explicados en la página) |
| Palabras por explicación | 61.2 | 52.7 |
| Latencia ampliada / primer nivel | 3.47 / 2.95 s | 3.55 / 3.64 s |
| *Juicio:* correcta / imprecisa / incorrecta | 17 / 3 / 6 | 13 / 9 / **4** |
| …incorrectas en **avanzado** (de 14) | **5** | **2** |
| …incorrectas en intermedio (de 10) | 1 | 2 |

Desaparecieron los errores ligados al **término**: "CO₂: un gas que quema y
quema" (2/2, ahora filtrado como símbolo) y la sensibilidad climática definida
en círculo (ahora la define bien el primer nivel y el segundo no la repite).
Aparece **"colinealidad"** bien definida (1/2).

Los errores que quedan **no son de elección del término**, sino de
definiciones de phi3 y de la frase "En pocas palabras":
- "Capas de hielo: hielo grueso **sobre el océano**" (están sobre tierra).
- "Ácido carbónico: … se convierte en **un gas**".
- "ENOS: fenómeno que afecta el clima **en el sur del mundo**".
- "por cada aumento de CO₂ la temperatura aumenta **2.31 grados**" (cifra mal usada).

**Lectura:** mejorar la elección del término **sí arregla los errores que
venían del término** (avanzado: 5 → 2 incorrectas), pero **no mejora la
calidad general del segundo nivel**: hay menos respuestas correctas (17 → 13)
y más imprecisas (3 → 9). Son dos corridas distintas, y phi3 varía de una a
otra en el mismo párrafo, así que la comparación global es solo indicativa.
Lo que queda es el límite del modelo al definir y al resumir.
