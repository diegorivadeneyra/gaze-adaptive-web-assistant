"""Resumen de las sesiones experimentales para el análisis.

Lee data/sessions/<sesion>_events.jsonl y <sesion>_gaze.csv (los escribe
backend/session_log.py) y genera en data/sessions/resumen/:
  - visitas.csv : una fila por visita a un elemento (cuánto se miró, si fue
                  relectura, su nivel y si se mostró o se suprimió la ayuda).
  - ayudas.csv  : una fila por ayuda mostrada o suprimida, con el texto exacto
                  y una columna "calificacion" vacía para calificarla a mano
                  (correcta / imprecisa / incorrecta).
  - paginas.csv : una fila por participante y página: condición, tiempo en la
                  página, relecturas, ayudas, calidad del seguimiento y, si el
                  participante marcó lo que le costó (marking.js), el ACIERTO
                  (de los elementos donde la regla dio ayuda, cuántos marcó) y
                  la COBERTURA (de los que marcó, a cuántos llegó la ayuda).
                  En "sin ayuda" cuenta la ayuda suprimida: la regla igual decidió.
Reglas completas: REGLAS_DEL_SISTEMA.md.
El plan de comparación (qué se compara y cómo) está en el README, sección 8.

Uso (desde la raíz del proyecto):
    python evaluation/analyze_sessions.py
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SESSIONS = ROOT / "data" / "sessions"
OUT = SESSIONS / "resumen"

VISIT_COLUMNS = ["sesion", "participante", "pagina", "condicion", "elemento", "tipo", "visita",
                 "relectura", "evento_lectura", "dwell_ms", "fijaciones", "tiempo_en_fijacion_ms",
                 "fijacion_media_ms", "pct_tiempo_en_fijacion", "leido_acumulado_ms", "esperado_ms",
                 "lectura_completa", "llego_al_final", "ritmo_ms_silaba", "nivel", "fuente_nivel",
                 "inflesz", "nivel_modelo", "elegible_ayuda", "ayuda", "senal", "ayuda_visible_ms",
                 "ayuda_mirada_ms", "marcado_dificil"]
HELP_COLUMNS = ["sesion", "participante", "pagina", "condicion", "help_id", "elemento", "estado",
                "nivel", "regla", "senal", "ratio_tiempo", "dwell_al_aparecer_ms", "relectura",
                "visible_ms", "mirada_dentro_ms", "reapariciones", "pedida", "nivel_ayuda",
                "concepto", "explicacion", "calificacion"]
PAGE_COLUMNS = ["sesion", "participante", "pagina", "condicion", "posicion", "duracion_ms", "pausa_ms", "elementos_distintos",
                "visitas", "relecturas", "visitas_elegibles", "relecturas_elegibles",
                "dwell_prom_elegibles_ms", "ayudas_mostradas", "ayudas_suprimidas",
                "ayudas_leidas", "disparos_en_low", "botones_ofrecidos", "ayudas_pedidas",
                "elementos_pedidos", "pedidos_que_la_regla_detecto",
                "marcados_dificiles", "elementos_con_ayuda",
                "aciertos", "acierto_pct", "cobertura_pct", "muestras_mirada", "muestras_invalidas_pct"]


def read_events(path):
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def gaze_quality(path):
    """(muestras, % inválidas) por página."""
    counts = defaultdict(lambda: [0, 0])
    if path.exists():
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                counts[row["page"]][0] += 1
                counts[row["page"]][1] += row["valid"] == "0"
    return {page: (n, round(100 * bad / n, 1) if n else None) for page, (n, bad) in counts.items()}


def summarize(events_path):
    session_id = events_path.name.removesuffix("_events.jsonl")
    events = list(read_events(events_path))
    start = next((e for e in events if e["type"] == "session_start"), {})
    participant = start.get("participant", "")
    plan = start.get("plan", {})
    order = start.get("order") or ["facil", "intermedio", "avanzado"]

    visits, helps = [], {}
    open_visit = {}          # página -> visita en curso
    last_visit = {}          # página -> última visita cerrada (para reading_state)
    pages = defaultdict(lambda: {"duracion_ms": None, "pausa_ms": None})
    marks = defaultdict(set)         # página -> elementos marcados como difíciles
    low_triggers = defaultdict(int)  # página -> disparos de la regla en Low
    offered = defaultdict(int)       # página -> botones "Ver ayuda" mostrados (a pedido)

    for e in events:
        page = e.get("page", "")
        base = {"sesion": session_id, "participante": participant, "pagina": page,
                "condicion": plan.get(page, "")}
        kind = e["type"]
        if kind == "element_enter":
            visit = {**base, "elemento": e["el"], "tipo": e.get("el_type", ""), "visita": e.get("visit"),
                     "relectura": int((e.get("visit") or 1) >= 2), "evento_lectura": e.get("reading_event") or "",
                     "dwell_ms": None, "fijaciones": "", "tiempo_en_fijacion_ms": "",
                     "fijacion_media_ms": "", "pct_tiempo_en_fijacion": "", "leido_acumulado_ms": "", "esperado_ms": "", "lectura_completa": "",
                     "llego_al_final": "", "ritmo_ms_silaba": "", "nivel": "",
                     "fuente_nivel": "", "inflesz": "", "nivel_modelo": "", "elegible_ayuda": 0,
                     "ayuda": "", "senal": "", "ayuda_visible_ms": "", "ayuda_mirada_ms": "",
                     "marcado_dificil": ""}
            visits.append(visit)
            open_visit[page] = visit
        elif kind == "element_exit":
            visit = open_visit.get(page)
            if visit and visit["elemento"] == e.get("el"):
                visit["dwell_ms"] = e.get("dwell_ms")
                # Qué parte de la visita detectó el I-DT como fijación: si es
                # baja con el Tobii, hay que ajustar sus parámetros.
                if e.get("fixation_count") is not None:
                    visit.update(fijaciones=e["fixation_count"], tiempo_en_fijacion_ms=e.get("fixation_ms"),
                                 fijacion_media_ms=e.get("mean_fixation_ms") or "",
                                 pct_tiempo_en_fijacion=round(100 * e["fixation_ms"] / e["dwell_ms"], 1)
                                 if e.get("dwell_ms") else "")
                last_visit[page] = open_visit.pop(page)
        elif kind == "reading_state":
            visit = last_visit.get(page)
            if visit and visit["elemento"] == e.get("el"):
                visit.update(leido_acumulado_ms=e.get("acc_ms"), esperado_ms=e.get("expected_ms") or "",
                             lectura_completa=int(bool(e.get("read_complete"))),
                             llego_al_final=int(bool(e.get("reached_end"))),
                             ritmo_ms_silaba=e.get("pace_ms_per_syllable"))
        elif kind == "help_offered":
            offered[page] += 1
        elif kind == "help_would_trigger_low":
            low_triggers[page] += 1
            visit = open_visit.get(page)
            if visit and visit["elemento"] == e.get("el"):
                visit["senal"] = f"{e.get('signal')} (Low, sin ayuda)"
        elif kind == "difficulty_marks":
            marks[page] = set(e.get("els") or [])
        elif kind == "analysis":
            visit = open_visit.get(page)
            if visit and visit["elemento"] == e.get("el"):
                visit.update(nivel=e.get("complexity", ""), fuente_nivel=e.get("difficulty_source", ""),
                             inflesz=e.get("inflesz") if e.get("inflesz") is not None else "",
                             nivel_modelo=e.get("llm_complexity") or "",
                             elegible_ayuda=int(e.get("action") == "tooltip"))
        elif kind in ("help_shown", "help_suppressed"):
            state = "mostrada" if kind == "help_shown" else "suprimida"
            helps[e["help_id"]] = {**base, "help_id": e["help_id"], "elemento": e.get("el"),
                                   "estado": state, "nivel": e.get("complexity"),
                                   "regla": e.get("rule", ""), "senal": e.get("signal", ""),
                                   "ratio_tiempo": e.get("ratio", ""),
                                   "dwell_al_aparecer_ms": e.get("dwell_ms"),
                                   "relectura": int(bool(e.get("revisit"))), "visible_ms": "",
                                   "mirada_dentro_ms": "", "concepto": e.get("concept") or ", ".join(e.get("terms") or []),
                                   "explicacion": e.get("explanation"), "calificacion": "", "reapariciones": 0,
                                   "pedida": int(bool(e.get("requested"))),
                                   "nivel_ayuda": e.get("help_level") or 1}
            visit = open_visit.get(page)
            if visit and visit["elemento"] == e.get("el"):
                visit["ayuda"] = state
                visit["senal"] = e.get("signal", "")
                visit["_help_id"] = e["help_id"]
        elif kind == "help_hidden" and e.get("help_id") in helps:
            # Si la ayuda reapareció (help_reshown, salida corta) se oculta
            # más de una vez: se suman los tiempos.
            h = helps[e["help_id"]]
            h["visible_ms"] = (h["visible_ms"] or 0) + (e.get("visible_ms") or 0)
            h["mirada_dentro_ms"] = (h["mirada_dentro_ms"] or 0) + (e.get("gaze_inside_ms") or 0)
        elif kind == "help_reshown" and e.get("help_id") in helps:
            helps[e["help_id"]]["reapariciones"] = helps[e["help_id"]].get("reapariciones", 0) + 1
        elif kind == "reading_end":
            # Duración de la LECTURA (hasta "Terminé"), sin la pausa ni el marcado.
            pages[page]["duracion_ms"] = e.get("duration_ms")
        elif kind == "pause_end":
            pages[page]["pausa_ms"] = e.get("duration_ms")
        elif kind == "page_exit" and pages[page]["duracion_ms"] is None:
            pages[page]["duracion_ms"] = e.get("duration_ms")   # sesiones anteriores a la pausa

    for visit in visits:
        if visit["pagina"] in marks:   # solo si el participante llegó a marcar
            visit["marcado_dificil"] = int(visit["elemento"] in marks[visit["pagina"]])
        help_row = helps.get(visit.pop("_help_id", None))
        if help_row and help_row["estado"] == "mostrada":
            visit["ayuda_visible_ms"] = help_row["visible_ms"]
            visit["ayuda_mirada_ms"] = help_row["mirada_dentro_ms"]

    quality = gaze_quality(SESSIONS / f"{session_id}_gaze.csv")
    page_rows = []
    for page in plan:
        pv = [v for v in visits if v["pagina"] == page]
        eligible = [v for v in pv if v["elegible_ayuda"]]
        dwell_eligible = [v["dwell_ms"] for v in eligible if v["dwell_ms"] is not None]
        ph = [h for h in helps.values() if h["pagina"] == page]
        n_gaze, invalid_pct = quality.get(page, (0, None))
        # La regla automática dio (o habría dado) ayuda; en "a pedido" no
        # cuentan las que pidió la persona (esas van aparte).
        helped = {h["elemento"] for h in ph if not h["pedida"]}
        requested = {h["elemento"] for h in ph if h["pedida"]}
        marked = marks[page] if page in marks else None
        hits = len(helped & marked) if marked is not None else ""
        if not pv and not n_gaze:
            continue  # página no visitada
        page_rows.append({
            "sesion": session_id, "participante": participant, "pagina": page,
            "condicion": plan.get(page, ""),
            # 1, 2 o 3: en qué lugar leyó esta página (el orden es aleatorio).
            "posicion": order.index(page) + 1 if page in order else "",
            "duracion_ms": pages[page]["duracion_ms"],
            "pausa_ms": pages[page]["pausa_ms"],
            "elementos_distintos": len({v["elemento"] for v in pv}), "visitas": len(pv),
            "relecturas": sum(v["relectura"] for v in pv), "visitas_elegibles": len(eligible),
            "relecturas_elegibles": sum(v["relectura"] for v in eligible),
            "dwell_prom_elegibles_ms": round(sum(dwell_eligible) / len(dwell_eligible)) if dwell_eligible else "",
            "ayudas_mostradas": sum(h["estado"] == "mostrada" for h in ph),
            "ayudas_suprimidas": sum(h["estado"] == "suprimida" for h in ph),
            # "Leída": la mirada estuvo al menos 500 ms dentro del tooltip
            # (criterio inicial, igual al umbral base de atención sostenida).
            "ayudas_leidas": sum(h["estado"] == "mostrada" and (h["mirada_dentro_ms"] or 0) >= 500 for h in ph),
            "disparos_en_low": low_triggers[page],
            "botones_ofrecidos": offered[page],
            "ayudas_pedidas": sum(bool(h["pedida"]) for h in ph),
            "elementos_pedidos": len(requested),
            # Validación del detector: de lo que la persona pidió, cuánto
            # habría detectado la regla automática.
            "pedidos_que_la_regla_detecto": len(requested & helped),
            "marcados_dificiles": len(marked) if marked is not None else "",
            "elementos_con_ayuda": len(helped),
            "aciertos": hits,
            "acierto_pct": round(100 * hits / len(helped), 1) if marked is not None and helped else "",
            "cobertura_pct": round(100 * hits / len(marked), 1) if marked else "",
            "muestras_mirada": n_gaze, "muestras_invalidas_pct": invalid_pct,
        })
    return visits, list(helps.values()), page_rows


def write(path, columns, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: Excel abre bien los acentos
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    files = sorted(SESSIONS.glob("*_events.jsonl"))
    if not files:
        sys.exit(f"No hay sesiones en {SESSIONS}")
    all_visits, all_helps, all_pages = [], [], []
    for path in files:
        visits, helps, page_rows = summarize(path)
        all_visits += visits
        all_helps += helps
        all_pages += page_rows
        print(f"{path.name}: {len(visits)} visitas, {len(helps)} ayudas, {len(page_rows)} páginas")
    OUT.mkdir(parents=True, exist_ok=True)
    write(OUT / "visitas.csv", VISIT_COLUMNS, all_visits)
    write(OUT / "ayudas.csv", HELP_COLUMNS, all_helps)
    write(OUT / "paginas.csv", PAGE_COLUMNS, all_pages)
    print(f"\nGuardado en {OUT.relative_to(ROOT)}: visitas.csv, ayudas.csv, paginas.csv")


if __name__ == "__main__":
    main()
