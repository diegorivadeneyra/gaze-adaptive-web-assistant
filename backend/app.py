from pathlib import Path

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from PIL import Image
from analyzers.text_analyzer import analyze_text
from analyzers.decision_engine import decide_action
from analyzers.image_analyzer import analyze_image, analyze_image_data
from analyzers.llm_utils import TEXT_MODEL, VISION_MODEL, ensure_ollama_models
import asyncio
import base64
import io
import json
import math
import socket
import threading
import time
import websockets

# ── Interruptor de fuente de coordenadas ────────────────────────────
# Cambia esta variable a mano y reinicia el servidor. No cambia en vivo
# a propósito (ver conversación previa: para pruebas de laboratorio es
# más seguro fijarlo antes de correr que dejar un switch en caliente).
INPUT_SOURCE_MOUSE = 1
INPUT_SOURCE_TOBII = 2

GAZE_INPUT_SOURCE = INPUT_SOURCE_MOUSE

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
GAZE_OFFSET_Y = -40

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


def _push_gaze_point(x, y, valid, timestamp_us=None):
    """Punto de entrada único para cualquier fuente de coordenadas de
    mirada (bridge TCP real o POST de prueba): valida y lo empuja de
    inmediato a los clientes WebSocket conectados."""
    valid = bool(valid) and isinstance(x, (int, float)) and isinstance(y, (int, float))
    payload = {
        "x": x if valid else None,
        "y": y if valid else None,
        "valid": valid,
        "timestamp_us": timestamp_us
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
    return jsonify({"input_source": _INPUT_SOURCE_NAMES[GAZE_INPUT_SOURCE]})


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
            analysis = analyze_text(content)
        elif content_type == "table":
            # La legibilidad (INFLESZ) mide texto corrido; en una tabla el
            # nivel lo juzga el modelo.
            analysis = analyze_text(content, use_readability=False)
        elif content_type == "image":
            analysis = analyze_image(content, context, design_level)
        elif content_type == "image_base64":
            analysis = analyze_image_data(content, context, design_level)
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
        _push_gaze_point(
            float(x) + GAZE_OFFSET_X,
            float(y) + GAZE_OFFSET_Y,
            valid_flag == "1",
            int(timestamp_us)
        )
    except ValueError:
        pass


def _tobii_socket_bridge():
    """Cliente TCP que se conecta a tobii_bridge/gaze_server.cpp (el proceso en
    C++ que sí habla con el eye tracker) y reenvía cada punto que manda vía
    _push_gaze_point. Reintenta la conexión si gaze_server.exe todavía no
    arrancó, o si se cae."""
    buffer = ""
    while True:
        try:
            print(f"[TOBII] Conectando a gaze_server.exe en {TOBII_BRIDGE_HOST}:{TOBII_BRIDGE_PORT}...")
            with socket.create_connection((TOBII_BRIDGE_HOST, TOBII_BRIDGE_PORT), timeout=5) as sock:
                print("[TOBII] Conectado. Recibiendo coordenadas...")
                while True:
                    chunk = sock.recv(1024)
                    if not chunk:
                        break
                    buffer += chunk.decode("utf-8", errors="ignore")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        _handle_tobii_line(line)
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
        analyze_text("El cielo es azul y el pasto es verde.")
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