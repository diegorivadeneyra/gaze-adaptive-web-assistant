"""Registro de sesiones en data/sessions/ (fuera de git; solo códigos, sin nombres):
  <sesion>_events.jsonl  un evento por línea (páginas, elementos, análisis, ayudas)
  <sesion>_gaze.csv      muestras crudas de la mirada, para recalcular después
Solo se agrega al final: si el sistema se cae, lo escrito no se pierde.
Resumen para el análisis: evaluation/analyze_sessions.py.
"""
import csv
import datetime
import json
import re
import subprocess
import threading
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SESSIONS_DIR = PROJECT_ROOT / "data" / "sessions"

PAGES = ("facil", "intermedio", "avanzado")
CONDITIONS = ("ayuda", "sin_ayuda", "a_pedido")
GAZE_COLUMNS = ["t_ms", "x", "y", "scroll_x", "scroll_y", "valid", "page"]

MAX_EVENTS_PER_BATCH = 5000
MAX_GAZE_PER_BATCH = 20000

_PARTICIPANT_RE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
_SESSION_RE = re.compile(r"^[A-Za-z0-9_-]{1,60}$")
_write_lock = threading.Lock()


def _git_version():
    """Commit del código con el que corrió la sesión (y si había cambios sin
    commit), para saber qué versión de prompts/umbrales vio cada participante."""
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=PROJECT_ROOT,
                                capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                               cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=5).stdout.strip()
        return {"commit": commit or None, "cambios_sin_commit": bool(dirty)}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "cambios_sin_commit": None}


def _paths(session_id):
    return (SESSIONS_DIR / f"{session_id}_events.jsonl",
            SESSIONS_DIR / f"{session_id}_gaze.csv")


def validate_start(data):
    """Devuelve (participante, plan, orden) o lanza ValueError con el motivo."""
    participant = data.get("participant")
    if not isinstance(participant, str) or not _PARTICIPANT_RE.match(participant):
        raise ValueError("Código de participante inválido (letras, números, - o _; máx. 20)")
    plan = data.get("plan")
    if not isinstance(plan, dict) or set(plan) != set(PAGES) or any(v not in CONDITIONS for v in plan.values()):
        raise ValueError(f"El plan debe asignar {PAGES} a {CONDITIONS}")
    # Orden de lectura (aleatorio por participante); sin orden = el de siempre.
    order = data.get("order") or list(PAGES)
    if not isinstance(order, list) or sorted(order) != sorted(PAGES):
        raise ValueError(f"El orden debe ser una permutación de {PAGES}")
    return participant, plan, order


def start_session(participant, plan, client_info, server_info, order=PAGES):
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_id = f"{participant}_{stamp}"
    suffix = 1
    while _paths(session_id)[0].exists():
        suffix += 1
        session_id = f"{participant}_{stamp}_{suffix}"

    event = {
        "type": "session_start",
        "t": int(datetime.datetime.now().timestamp() * 1000),
        "session_id": session_id,
        "participant": participant,
        "plan": plan,
        "order": list(order),
        "client": client_info if isinstance(client_info, dict) else {},
        "server": {**server_info, **_git_version()},
    }
    events_path, gaze_path = _paths(session_id)
    with _write_lock:
        with events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        with gaze_path.open("w", newline="", encoding="utf-8") as f:
            csv.writer(f).writerow(GAZE_COLUMNS)
    return session_id


def append(data):
    """Agrega un lote de eventos y de muestras de mirada a la sesión.
    Devuelve (n_eventos, n_muestras) o lanza ValueError."""
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not _SESSION_RE.match(session_id):
        raise ValueError("session_id inválido")
    events_path, gaze_path = _paths(session_id)
    if not events_path.exists():
        raise ValueError("La sesión no existe (¿se inició desde index.html?)")

    events = data.get("events") or []
    gaze = data.get("gaze") or []
    page = data.get("page") if data.get("page") in PAGES else ""
    if not isinstance(events, list) or not isinstance(gaze, list):
        raise ValueError("events y gaze deben ser listas")
    if len(events) > MAX_EVENTS_PER_BATCH or len(gaze) > MAX_GAZE_PER_BATCH:
        raise ValueError("Lote demasiado grande")

    received = int(datetime.datetime.now().timestamp() * 1000)
    event_lines = [json.dumps({**e, "t_server": received}, ensure_ascii=False)
                   for e in events if isinstance(e, dict) and isinstance(e.get("type"), str)]
    gaze_rows = [row[:6] + [page] for row in gaze
                 if isinstance(row, list) and len(row) >= 6]

    with _write_lock:
        if event_lines:
            with events_path.open("a", encoding="utf-8") as f:
                f.write("\n".join(event_lines) + "\n")
        if gaze_rows:
            with gaze_path.open("a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(gaze_rows)
    return len(event_lines), len(gaze_rows)
