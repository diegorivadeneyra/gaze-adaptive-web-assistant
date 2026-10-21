"""Política de ayuda: es la ÚNICA fuente de los umbrales que deciden cuándo
se muestra la ayuda. El frontend los recibe (en /analyze y en /config) y solo
los obedece. Las reglas completas, explicadas, están en REGLAS_DEL_SISTEMA.md.

Dos decisiones separadas:
  1. ¿Hay ayuda disponible? La decide el CONTENIDO: nivel Low no tiene ayuda;
     Medium y High sí (HELP_POLICY).
  2. ¿Esta persona la necesita ahora? La decide su CONDUCTA de lectura
     (READING_POLICY), en texto corrido:
       - "atascado": lleva en el párrafo 1.5 veces el tiempo que le tomaría
         leerlo (sílabas × su ritmo × factor del nivel), y a más tardar ese
         tiempo + 15 s;
       - "relectura": vuelve al párrafo después de haberlo leído (≥ 70 % del
         tiempo esperado y la mirada llegó al final del párrafo);
       - "relectura en el párrafo": ya lo leyó y, sin salir, vuelve a su
         primer tercio.
     El ritmo arranca en el promedio general y se adapta a la persona mientras
     lee párrafos fáciles (sin medición previa).

En tablas, gráficas e imágenes ("palabras" no tiene sentido ahí) se mantiene
la regla anterior por tiempo fijo: Medium tras 2 s, High tras 0.5 s y 0.5 s si
es una relectura.

Todos los valores son criterios INICIALES, a calibrar con la prueba piloto.
"""

BASE_DWELL_MS = 500
HELP_POLICY = {
    "High":   {"mode": "summary", "min_dwell_ms": BASE_DWELL_MS},
    "Medium": {"mode": "brief",   "min_dwell_ms": 2000},
}
REVISIT_MIN_DWELL_MS = BASE_DWELL_MS

READING_POLICY = {
    # Ritmo promedio de partida: 140 ms por sílaba ≈ 214 palabras/min con
    # ~2 sílabas por palabra (medido en las páginas: 1.85 fácil, 2.31
    # intermedio, 2.48 avanzado). VERIFICADO el 2026-10-11 en Brysbaert (2019,
    # J. Memory and Language 109, Tabla 5): lectura silenciosa en español =
    # 278 palabras/min (5 estudios), en inglés no ficción 238. O sea, 140 es
    # más lento que ese promedio (278 ≈ 108 ms/sílaba). Es conservador a
    # propósito: quien sabe que le harán preguntas lee más lento (Brysbaert
    # 2019, sobre Carver y Kemper y Sumner). A calibrar con el piloto.
    "base_ms_per_syllable": 140,
    # Cuánto más lento se lee, aunque se entienda, según el nivel del texto.
    # Ojo: las sílabas ya alargan el tiempo de los textos difíciles (palabras
    # más largas); el factor se suma a eso. A calibrar con el piloto.
    "level_factor": {"Low": 1.0, "Medium": 1.3, "High": 1.6},
    # Atascado: tiempo acumulado >= 1.5 × tiempo esperado, y a más tardar
    # esperado + 15 s. Sin ese tope, en los párrafos largos de avanzado había
    # que quedarse 43–68 s (lo notó el usuario al probarlo, 2026-10-11).
    "stuck_ratio": 1.5,
    "stuck_max_extra_ms": 15000,
    # Relectura en el párrafo: tras leerlo, la mirada vuelve a su primer
    # tercio y se queda ahí al menos 1.5 s. Con 0.4 s, quien solo vuelve un
    # momento a revisar un dato recibía ayuda (38 % en la simulación); con
    # 1.5 s, 0 %, a cambio de cobertura 95 → 90 % y +1.3 s de demora. Supone
    # que releer una oración toma más que mirar un dato: a calibrar en el piloto.
    "start_region": 1 / 3,
    "reread_start_min_ms": 1500,
    # Solo cuenta el tiempo con FIJACIÓN en el primer tercio (regresión, el
    # indicador clásico de dificultad). Si el piloto muestra que el Tobii
    # detecta pocas fijaciones al leer, poner False (cuenta cualquier mirada).
    "reread_requires_fixation": True,
    # Segundo nivel de ayuda: tras la primera ayuda, "atascado" otra vez si
    # sigue en el párrafo 1.0 × su tiempo esperado más. Con 0.75, en Medium
    # una sola relectura completa a ritmo normal (1/1.3 ≈ 0.77 del esperado)
    # ya lo daba (prueba en el navegador, 2026-10-11). La relectura (volviendo
    # o dentro del párrafo) también lo dispara.
    "level2_extra_fraction": 1.0,
    # "Lo leyó": la mirada está en el último tercio cuando ya acumuló >= 40 %
    # del tiempo esperado. Con 70 %, un lector rápido cuyo ritmo aún no se
    # adaptó necesitaba ~2 lecturas para que contara (lo notó el usuario);
    # 40 % no agregó ayudas innecesarias en la simulación. Bajar también los
    # factores o el umbral de atascado sí las agregaba (hasta 45–75 %).
    "read_fraction": 0.4,
    # Final del párrafo = su último tercio (vertical). Bloques de menos de
    # ~3 líneas cuentan como "llegó al final" de inmediato.
    "end_region": 1 / 3,
    "end_min_height_px": 60,
    # Salir menos de 5 s no corta la lectura (ruido del Tobii, mirar una
    # gráfica que el texto menciona); salir más, sí.
    "revisit_gap_ms": 5000,
    # Ritmo adaptativo: se actualiza con párrafos Low leídos hasta el final,
    # sin señales, cuyo tiempo observado esté entre 0.4 y 2 veces el
    # esperado (fuera de eso es hojeo o distracción). Media móvil con peso
    # 0.3, acotada entre 0.6 y 1.8 veces el ritmo base.
    "pace_alpha": 0.3,
    "pace_min_fraction": 0.4,
    "pace_max_fraction": 2.0,
    "pace_min_syllables": 20,
    "pace_bounds": [0.6, 1.8],
}


def decide_action(complexity, needs_assistance):
    policy = HELP_POLICY.get(complexity)
    if not needs_assistance or policy is None:
        return {"action": "none", "mode": "none", "min_dwell_ms": 0, "revisit_min_dwell_ms": 0}

    return {
        "action": "tooltip",
        "mode": policy["mode"],
        "min_dwell_ms": policy["min_dwell_ms"],
        "revisit_min_dwell_ms": min(policy["min_dwell_ms"], REVISIT_MIN_DWELL_MS),
    }
