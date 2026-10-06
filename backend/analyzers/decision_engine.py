"""Política de ayuda: dado el nivel de dificultad de un elemento, decide si se
ofrece ayuda y cuánto tiempo de atención sostenida (dwell) se exige antes de
mostrarla. Es la ÚNICA fuente de estos umbrales: el frontend los recibe en la
respuesta de /analyze y solo los obedece.

  Low     -> sin ayuda.
  Medium  -> ayuda REACTIVA: aparece tras 2 s de atención sostenida en el
             elemento. Filtra el "hojeo" (pasar la vista rápido por varios
             bloques) sin hacer esperar a quien sí está leyendo.
  High    -> ayuda PROACTIVA: aparece desde el umbral base de 0.5 s (el
             mismo que dispara el análisis), porque el contenido es muy denso
             y esperar solo lo haría llegar tarde.

  Relectura -> si el usuario vuelve a un elemento que ya había mirado
               (regresión, señal conocida de dificultad de lectura), la ayuda
               de nivel Medium se ofrece desde 0.5 s en vez de 2 s.

Los valores de dwell son criterios de diseño iniciales, a calibrar con los
datos de las pruebas piloto (ver README, "Criterios para la experimentación").
"""

BASE_DWELL_MS = 500
HELP_POLICY = {
    "High":   {"mode": "summary", "min_dwell_ms": BASE_DWELL_MS},
    "Medium": {"mode": "brief",   "min_dwell_ms": 2000},
}
REVISIT_MIN_DWELL_MS = BASE_DWELL_MS


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
