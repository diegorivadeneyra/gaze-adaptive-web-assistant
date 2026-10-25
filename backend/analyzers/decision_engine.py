"""Política de ayuda: única fuente de los umbrales (el frontend los recibe por
/analyze y /config). Explicación y origen de cada valor: REGLAS_DEL_SISTEMA.md §4.

1. ¿Hay ayuda? La decide el contenido: Low no tiene; Medium y High sí (HELP_POLICY).
2. ¿La necesita ahora? En texto corrido, la conducta de lectura (READING_POLICY):
   atascado, relectura al volver o relectura dentro del párrafo.
   En tablas, gráficas e imágenes: tiempo fijo por nivel.
Los valores son criterios iniciales, a calibrar con el piloto.
"""

BASE_DWELL_MS = 500
HELP_POLICY = {
    "High":   {"mode": "summary", "min_dwell_ms": BASE_DWELL_MS},
    "Medium": {"mode": "brief",   "min_dwell_ms": 2000},
}
REVISIT_MIN_DWELL_MS = BASE_DWELL_MS

READING_POLICY = {
    # Ritmo de partida en ms por sílaba. Conservador: el promedio en español es
    # ~108 (278 palabras/min, Brysbaert 2019, Tabla 5).
    "base_ms_per_syllable": 140,
    # Cuánto más lento se lee cada nivel aunque se entienda.
    "level_factor": {"Low": 1.0, "Medium": 1.3, "High": 1.6},
    # Atascado: >= 1.5 × el tiempo esperado, como máximo esperado + 15 s.
    "stuck_ratio": 1.5,
    "stuck_max_extra_ms": 15000,
    # Relectura en el párrafo: tras leerlo, >= 1.5 s de fijaciones en su primer tercio.
    "start_region": 1 / 3,
    "reread_start_min_ms": 1500,
    "reread_requires_fixation": True,
    # Segundo nivel: tras la primera ayuda, 1.0 × el esperado más (o una relectura).
    "level2_extra_fraction": 1.0,
    # "Lo leyó": en el último tercio con >= 40 % del tiempo esperado acumulado.
    "read_fraction": 0.4,
    "end_region": 1 / 3,
    "end_min_height_px": 60,     # bloques más bajos cuentan como "llegó al final"
    # Salir menos de 5 s no corta la lectura.
    "revisit_gap_ms": 5000,
    # Ritmo adaptativo: aprende de párrafos de cualquier nivel leídos completos y
    # sin señales; mediana de las últimas 5 medidas (tiempo / sílabas / factor),
    # el ritmo base cuenta como medida mientras haya menos de 3, y solo sube
    # 10 % por lectura. False = regla anterior (solo Low, media móvil pace_alpha).
    "pace_from_all_levels": True,
    "pace_window": 5,
    "pace_prior_until": 3,
    "pace_max_increase": 0.10,
    "pace_alpha": 0.3,
    "pace_min_fraction": 0.4,    # medidas válidas: entre 0.4 y 2 × el esperado
    "pace_max_fraction": 2.0,
    "pace_min_syllables": 20,
    "pace_bounds": [0.6, 1.8],   # límites respecto al ritmo base
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
