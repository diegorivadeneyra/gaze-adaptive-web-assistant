from pathlib import Path

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from PIL import Image
from analyzers.text_analyzer import analyze_text
from analyzers.decision_engine import decide_action
from analyzers.image_analyzer import analyze_image, analyze_image_data
from analyzers.llm_utils import TEXT_MODEL, VISION_MODEL, ensure_ollama_models
from analyzers.decision_engine import HELP_POLICY, READING_POLICY, REVISIT_MIN_DWELL_MS
from analyzers.readability import count_text_syllables
from analyzers.expanded_help import expand_text
import session_log
import asyncio
import atexit
import subprocess
import base64
import io
import json
import math
import os
import socket
import sys
import threading
import time
import websockets

# Los print muestran términos del modelo (p. ej. "CO₂"). Si la consola no es
# UTF-8 (salida redirigida en Windows = cp1252), el print lanzaba
# UnicodeEncodeError y la ruta respondía 500 sin dar la ayuda.
for _stream in (sys.stdout, sys.stderr):
    _stream.reconfigure(encoding="utf-8", errors="replace")

# ── Interruptor de fuente de coordenadas ────────────────────────────
# Cambia esta variable a mano y reinicia el servidor. No cambia en vivo
# a propósito (ver conversación previa: para pruebas de laboratorio es
# más seguro fijarlo antes de correr que dejar un switch en caliente).
INPUT_SOURCE_MOUSE = 1
INPUT_SOURCE_TOBII = 2

GAZE_INPUT_SOURCE = INPUT_SOURCE_TOBII
# Solo para pruebas sin tocar el código: GAZE_SOURCE=tobii python app.py
if os.environ.get("GAZE_SOURCE", "").lower() in ("tobii", "mouse"):
    GAZE_INPUT_SOURCE = INPUT_SOURCE_TOBII if os.environ["GAZE_SOURCE"].lower() == "tobii" else INPUT_SOURCE_MOUSE

_INPUT_SOURCE_NAMES = {INPUT_SOURCE_MOUSE: "mouse", INPUT_SOURCE_TOBII: "tobii"}
if GAZE_INPUT_SOURCE not in _INPUT_SOURCE_NAMES:
    GAZE_INPUT_SOURCE = INPUT_SOURCE_MOUSE

# Host/puerto donde tobii_bridge/gaze_server.cpp abre su socket TCP.
TOBII_BRIDGE_HOST = "127.0.0.1"
TOBII_BRIDGE_PORT = 5555

# Host/puerto donde este backend expone el socket de mirada al frontend
# (reemplaza el polling por HTTP: el Tobii entrega datos a ~90Hz y
# preguntar "¿hay algo nuevo?" cada 100ms descartaba ~90% de las muestras).
WS_HOST = "127.0.0.1"
WS_PORT = 5600

# Corrección manual de desfase sistemático (en píxeles), aplicada a cada
# punto que llega del Tobii ANTES de mandarlo al frontend. Si el sistema
# detecta consistentemente más abajo/arriba/a un lado de donde realmente
# se mira (no ruido aleatorio, sino siempre en la misma dirección), ajusta
# estos valores a mano y reinicia este script — no hace falta recompilar
# gaze_server.cpp. Ej.: si detecta ~40px más abajo de lo real, usa -40.
GAZE_OFFSET_X = 0
GAZE_OFFSET_Y = 0   # antes −40 (manual); ahora lo corrige la comprobación de 5 puntos (calibracion.html)


def _screen_size():
    """Resolución de pantalla que usa gaze_server.cpp para pasar la mirada a
    píxeles (GetSystemMetrics, igual que aquí). Sirve para volver a la
    proporción de pantalla (0–1), que el navegador convierte según el equipo."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
    except Exception:   # no es Windows
        return None


TOBII_SCREEN = _screen_size()

def _warmup_image_b64():
    """Imagen en blanco de 64x64 usada solo para precalentar el modelo de
    visión (evita depender de una descarga de red al iniciar el servidor)."""
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"

app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
CORS(app)

# ── Puente de coordenadas del Tobii 5 (push por WebSocket) ─────────────
# Cada punto que llega (del socket TCP de tobii_bridge/gaze_server.cpp, o de
# un POST manual de prueba vía simulate_gaze.py) se reenvía de inmediato a
# todos los navegadores conectados por WebSocket — ya no se guarda un
# "último valor" para que el frontend lo vaya a buscar por polling, porque
# eso era lo que tiraba al piso la frecuencia real de muestreo del Tobii.
_ws_clients = set()
_ws_loop = None  # se asigna cuando arranca el hilo del servidor WS


async def _ws_handler(websocket):
    _ws_clients.add(websocket)
    try:
        async for _ in websocket:
            pass  # no se espera nada del cliente, solo se le manda data
    finally:
        _ws_clients.discard(websocket)


async def _ws_broadcast(payload):
    if not _ws_clients:
        return
    message = json.dumps(payload)
    await asyncio.gather(
        *(ws.send(message) for ws in list(_ws_clients)),
        return_exceptions=True
    )


def _push_gaze_point(x, y, valid, timestamp_us=None, nx=None, ny=None):
    """Punto de entrada único para cualquier fuente de coordenadas de
    mirada (bridge TCP real o POST de prueba): valida y lo empuja de
    inmediato a los clientes WebSocket conectados."""
    valid = bool(valid) and isinstance(x, (int, float)) and isinstance(y, (int, float))
    payload = {
        "x": x if valid else None,
        "y": y if valid else None,
        "valid": valid,
        "timestamp_us": timestamp_us,
        # Proporción de pantalla (0–1): el navegador la pasa a la página según el
        # equipo (gaze_mapping.js). x, y quedan por compatibilidad.
        "nx": nx if valid else None,
        "ny": ny if valid else None,
    }
    if _ws_loop is not None:
        asyncio.run_coroutine_threadsafe(_ws_broadcast(payload), _ws_loop)


def _run_websocket_server():
    global _ws_loop
    _ws_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_ws_loop)

    async def main():
        async with websockets.serve(_ws_handler, WS_HOST, WS_PORT):
            print(f"[WS] Servidor de mirada en ws://{WS_HOST}:{WS_PORT}")
            await asyncio.Future()  # corre para siempre

    _ws_loop.run_until_complete(main())


@app.route("/config", methods=["GET"])
def get_config():
    # La regla de lectura (READING_POLICY) también vive solo en el backend.
    return jsonify({"input_source": _INPUT_SOURCE_NAMES[GAZE_INPUT_SOURCE],
                    "reading_policy": READING_POLICY,
                    "tobii_screen": TOBII_SCREEN})


@app.route("/gaze-latest", methods=["POST"])
def post_gaze_latest():
    """Endpoint de prueba (ver simulate_gaze.py) para simular al Tobii sin
    el hardware conectado — empuja el punto por el mismo camino que usa
    el bridge real."""
    data = request.get_json(silent=True) or {}
    _push_gaze_point(data.get("x"), data.get("y"), data.get("valid", True), data.get("timestamp_us"))
    return jsonify({"ok": True})

@app.route("/")
def home():
    return send_file(FRONTEND_DIR / "index.html")


# ── Segundo nivel de ayuda (ver analyzers/expanded_help.py) ─────────
@app.route("/expand", methods=["POST"])
def expand():
    data = request.get_json(silent=True) or {}
    content = data.get("content")
    if not isinstance(content, str) or not content.strip() or len(content) > 12000:
        return jsonify({"error": "content debe ser texto"}), 400
    section = data.get("section") if isinstance(data.get("section"), str) else ""
    defined = data.get("already_defined") if isinstance(data.get("already_defined"), str) else ""
    page_terms = data.get("defined_terms")
    page_terms = [t.strip()[:120] for t in page_terms[:30] if isinstance(t, str) and t.strip()] \
        if isinstance(page_terms, list) else []
    result = expand_text(content, section.strip()[:150], defined.strip()[:120], page_terms)
    print(f"[AYUDA 2] {result.get('processing_time')}s · términos {[t['term'] for t in result.get('terms', [])]}"
          f" · descartados {result.get('discarded_terms')}")
    return jsonify(result), (502 if "error" in result else 200)


# ── Registro de sesiones (ver backend/session_log.py) ──────────────
MAX_LOG_BODY_BYTES = 5_000_000


@app.route("/session/start", methods=["POST"])
def session_start():
    data = request.get_json(silent=True) or {}
    try:
        participant, plan, order = session_log.validate_start(data)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    server_info = {
        "input_source": _INPUT_SOURCE_NAMES[GAZE_INPUT_SOURCE],
        "text_model": TEXT_MODEL,
        "vision_model": VISION_MODEL,
        "help_policy": HELP_POLICY,
        "revisit_min_dwell_ms": REVISIT_MIN_DWELL_MS,
        "reading_policy": READING_POLICY,
        "gaze_offset_y": GAZE_OFFSET_Y,
    }
    session_id = session_log.start_session(participant, plan, data.get("client"), server_info, order)
    print(f"[SESION] Iniciada {session_id} · orden {order} · plan {plan}")
    return jsonify({"session_id": session_id})


@app.route("/log", methods=["POST"])
def log_events():
    # Llega como text/plain (también desde navigator.sendBeacon al salir de
    # la página): así el navegador no hace la petición previa de CORS.
    raw = request.get_data(cache=False, as_text=True)
    if len(raw) > MAX_LOG_BODY_BYTES:
        return jsonify({"error": "Lote demasiado grande"}), 413
    try:
        n_events, n_gaze = session_log.append(json.loads(raw))
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"ok": True, "events": n_events, "gaze": n_gaze})


@app.route("/analyze", methods=["POST"])
def analyze():
    try:
        data = request.get_json(silent=True)
        
        if not data:
            return jsonify({"error": "No data received"}), 400

        content = data.get("content", "")
        content_type = data.get("content_type", "text")
        dwell_time = data.get("dwell_time", 0)
        context = data.get("context", "")
        # Nivel diseñado de la figura (data-level); el analizador lo valida.
        design_level = data.get("design_level")
        # Textos escritos en una gráfica SVG (valores, ejes, etiquetas).
        chart_text = data.get("chart_text", "")
        chart_text = chart_text.strip()[:600] if isinstance(chart_text, str) else ""
        # Contexto de la página: título del contenido y sección del elemento.
        page_context = {
            key: value.strip()[:150]
            for key, value in (("title", data.get("page_title")), ("section", data.get("section")))
            if isinstance(value, str) and value.strip()
        }

        # Términos ya explicados en esta página (el navegador los lleva):
        # el análisis de texto no vuelve a elegirlos. term_selection solo lo
        # usan los scripts de evaluación para comparar variantes.
        defined_terms = data.get("defined_terms")
        defined_terms = [t.strip()[:120] for t in defined_terms[:30] if isinstance(t, str) and t.strip()]             if isinstance(defined_terms, list) else []
        term_selection = data.get("term_selection") if isinstance(data.get("term_selection"), str) else None

        if not isinstance(content, str):
            return jsonify({"error": "Content must be a string"}), 400
        if not isinstance(context, str):
            context = ""
        context = context.strip()[:300]
        if not isinstance(content_type, str) or content_type not in {"text", "table", "image", "image_base64"}:
            return jsonify({"error": "Unsupported content type"}), 400
        try:
            dwell_time = float(dwell_time)
        except (TypeError, ValueError):
            return jsonify({"error": "dwell_time must be a number"}), 400
        if not math.isfinite(dwell_time) or dwell_time < 0:
            return jsonify({"error": "dwell_time must be finite and non-negative"}), 400

        content = content.strip()
        # Las imágenes base64 (gráficas/tablas renderizadas en el cliente) son más
        # pesadas que texto plano, así que usan un límite propio más generoso.
        max_length = 2_000_000 if content_type == "image_base64" else 12000
        if len(content) > max_length:
            return jsonify({"error": "Content is too long"}), 413

        if not content:
            return jsonify({
                "concept": "",
                "complexity": "Low",
                "needs_assistance": False,
                "explanation": "",
                "action": "none"
            })

        start_time = time.time()

        if content_type == "text":
            analysis = analyze_text(content, page_context=page_context,
                                    defined_terms=defined_terms, term_selection=term_selection)
        elif content_type == "table":
            # La legibilidad (INFLESZ) mide texto corrido; en una tabla el
            # nivel lo juzga el modelo.
            analysis = analyze_text(content, use_readability=False, page_context=page_context)
        elif content_type == "image":
            analysis = analyze_image(content, context, design_level, page_context)
        elif content_type == "image_base64":
            analysis = analyze_image_data(content, context, design_level, chart_text, page_context)
        processing_time = round(time.time() - start_time, 2)

        # Llegó una petición más nueva mientras esta esperaba/generaba: el
        # frontend ya no la necesita, no hay nada útil que devolver.
        if analysis.get("stale"):
            return jsonify({"stale": True, "action": "none", "processing_time": processing_time})

        decision = decide_action(
            analysis["complexity"],
            analysis["needs_assistance"]
        )

        print("\n===== DATOS RECIBIDOS =====")
        print(f"Dwell Time: {dwell_time}s")
        print(f"Content Type: {content_type}")
        print(f"Processing Time: {processing_time}s")
        print("===========================")
        print("\n===== ANÁLISIS =====")
        print(f"Concept: {analysis['concept']}")
        print(f"Complexity: {analysis['complexity']} (fuente: {analysis.get('difficulty_source', 'modelo')}"
              f", INFLESZ: {analysis.get('inflesz', '—')}, modelo dijo: {analysis.get('llm_complexity', '—')})")
        print(f"Needs Assistance: {analysis['needs_assistance']}")
        print(f"Decision: {decision['action']} (dwell mínimo {decision['min_dwell_ms']} ms)")
        print("====================\n")

        return jsonify({
            "concept": analysis["concept"],
            "complexity": analysis["complexity"],
            "needs_assistance": analysis["needs_assistance"],
            "explanation": analysis["explanation"],
            "action": decision["action"],
            "mode": decision["mode"],
            "min_dwell_ms": decision["min_dwell_ms"],
            "revisit_min_dwell_ms": decision["revisit_min_dwell_ms"],
            "difficulty_source": analysis.get("difficulty_source", "modelo"),
            "llm_complexity": analysis.get("llm_complexity"),
            "inflesz": analysis.get("inflesz"),
            "inflesz_label": analysis.get("inflesz_label"),
            "help_blocked": analysis.get("help_blocked"),
            "term_selection": analysis.get("term_selection"),
            "term_candidates": analysis.get("term_candidates"),
            "term_discarded": analysis.get("term_discarded"),
            # Solo texto corrido: base del tiempo de lectura esperado.
            "syllables": count_text_syllables(content) if content_type == "text" else None,
            "processing_time": processing_time
        })

    except Exception as e:
        print(f"ERROR en /analyze: {e}")
        return jsonify({
            "concept": "Error",
            "complexity": "Medium",
            "needs_assistance": False,
            "explanation": "Error interno del servidor.",
            "action": "none"
        }), 500


def _handle_tobii_line(line):
    """Parsea una linea 'x,y,timestamp_us,valid' enviada por gaze_server.cpp."""
    parts = line.strip().split(",")
    if len(parts) != 4:
        return
    try:
        x, y, timestamp_us, valid_flag = parts
        x, y = float(x), float(y)
        nx = x / TOBII_SCREEN[0] if TOBII_SCREEN else None
        ny = y / TOBII_SCREEN[1] if TOBII_SCREEN else None
        _push_gaze_point(
            x + GAZE_OFFSET_X,
            y + GAZE_OFFSET_Y,
            valid_flag == "1",
            int(timestamp_us),
            nx, ny
        )
    except ValueError:
        pass


# ── Puente del Tobii (gaze_server.exe) lanzado por este servidor ────
# En modo Tobii, app.py abre el puente en OTRA ventana (no hace falta abrirlo
# a mano) y lo cierra al terminar. El puente acepta UNA sola conexión: si se
# desconecta, queda inútil, así que se cierra y se abre uno nuevo.
BRIDGE_AUTOSTART = True
_bridge_proc = None


def _bridge_exe():
    base = PROJECT_ROOT / "tobii_bridge"
    # bin/ = versión Release ya compilada que viene en el repositorio (corre sin
    # Visual Studio, p. ej. en la laptop de las pruebas); luego, lo compilado aquí.
    for folder in ("bin", "Release", "Debug"):
        exe = base / folder / "gaze_server.exe"
        if exe.exists():
            return exe
    return None


def _stop_bridge():
    global _bridge_proc
    if _bridge_proc is not None and _bridge_proc.poll() is None:
        _bridge_proc.terminate()
    _bridge_proc = None


def _start_bridge():
    """Cierra puentes viejos (de una ejecución anterior) y abre uno nuevo."""
    global _bridge_proc
    exe = _bridge_exe()
    if exe is None:
        print("[TOBII] No se encontró tobii_bridge/(Release|Debug)/gaze_server.exe: "
              "compílalo con Visual Studio (ver tobii_bridge/README.md) o ábrelo a mano.")
        return False
    _stop_bridge()
    subprocess.run(["taskkill", "/F", "/IM", "gaze_server.exe"], capture_output=True)
    _bridge_proc = subprocess.Popen([str(exe)], cwd=str(exe.parent),
                                    creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0))
    print(f"[TOBII] Puente abierto en otra ventana: {exe.relative_to(PROJECT_ROOT)}")
    time.sleep(1.5)   # tiempo para que empiece a escuchar
    return True


atexit.register(_stop_bridge)


def _tobii_socket_bridge():
    """Cliente TCP que se conecta a tobii_bridge/gaze_server.cpp (el proceso en
    C++ que sí habla con el eye tracker) y reenvía cada punto que manda vía
    _push_gaze_point. Si el puente no está abierto (o se cerró), lo abre."""
    buffer = ""
    while True:
        if BRIDGE_AUTOSTART and (_bridge_proc is None or _bridge_proc.poll() is not None):
            if _bridge_proc is not None:
                print("[TOBII] El puente se cerró (¿Tobii desconectado?). Se vuelve a abrir.")
            _start_bridge()
        try:
            print(f"[TOBII] Conectando a gaze_server.exe en {TOBII_BRIDGE_HOST}:{TOBII_BRIDGE_PORT}...")
            with socket.create_connection((TOBII_BRIDGE_HOST, TOBII_BRIDGE_PORT), timeout=5) as sock:
                # Sin tiempo límite al RECIBIR: si la persona se aparta y el
                # Tobii deja de enviar unos segundos, no se corta la conexión
                # (el puente acepta una sola; cortarla obligaba a reiniciar).
                sock.settimeout(None)
                print("[TOBII] Conectado. Recibiendo coordenadas...")
                while True:
                    chunk = sock.recv(1024)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", errors="ignore")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        _handle_tobii_line(line)
            print("[TOBII] El puente cortó la conexión. Se abre uno nuevo.")
            if BRIDGE_AUTOSTART:
                _stop_bridge()
        except (ConnectionRefusedError, OSError, socket.timeout) as e:
            print(f"[TOBII] Sin conexión con gaze_server.exe ({e}). Reintentando en 3s...")
        time.sleep(3)


def _warmup_models():
    """Descarga los modelos de Ollama que falten en esta computadora (solo
    la primera vez) y los carga antes de la primera petición real, para que
    la lentitud de la carga en frío no la sufra el primer usuario que mira la página."""
    try:
        if not ensure_ollama_models([TEXT_MODEL, VISION_MODEL]):
            return
        print("\n[WARMUP] Precalentando modelos...")
        # use_readability=False: con la legibilidad, esta frase es Low y no
        # llegaba a phi3, así que phi3 NO se precalentaba (medido el
        # 2026-10-17: la primera ayuda de la sesión salía con el mensaje
        # genérico por exceder el tiempo límite mientras cargaba el modelo).
        analyze_text("El cielo es azul y el pasto es verde.", use_readability=False)
        analyze_image_data(_warmup_image_b64(), "")
        print("[WARMUP] Modelos listos.\n")
    except Exception as e:
        print(f"[WARMUP] Falló el precalentado (no crítico): {e}")


if __name__ == "__main__":
    print(f"[CONFIG] Fuente de coordenadas: {_INPUT_SOURCE_NAMES[GAZE_INPUT_SOURCE]}")
    threading.Thread(target=_warmup_models, daemon=True).start()
    if GAZE_INPUT_SOURCE == INPUT_SOURCE_TOBII:
        threading.Thread(target=_run_websocket_server, daemon=True).start()
        threading.Thread(target=_tobii_socket_bridge, daemon=True).start()
    app.run(debug=False)