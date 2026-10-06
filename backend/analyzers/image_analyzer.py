import base64
import binascii
import ipaddress
import json
import socket
import threading
import time
from io import BytesIO
from urllib.parse import urlparse

import requests
from PIL import Image, UnidentifiedImageError

from analyzers.llm_utils import (
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    VISION_MODEL,
    extract_json,
    extract_partial_analysis,
    normalize_analysis,
)
from analyzers.text_analyzer import detect_language

OLLAMA_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"

MAX_IMAGE_SIDE = 512
MAX_NEW_TOKENS = 120
GENERATION_TIMEOUT_S = 25
CONTEXT_MAX_CHARS = 300

# Nivel diseñado de la figura (atributo data-design-level en el HTML). Si viene, el
# nivel deja de ser juicio del modelo: con temperatura 0 Qwen es estable, pero
# su nivel cambió de Medium a Low en la gráfica de avanzado solo por pasar el
# prompt a español (ver README, sección 7). Lo que dice el modelo se guarda en
# llm_complexity para medir el acuerdo.
VALID_DESIGN_LEVELS = {"Low", "Medium", "High"}

# Una sola inferencia a la vez, y "el último gana": el frontend cancela su
# petición al cambiar de elemento, pero el backend no se entera, así que sin
# esto se acumulaban análisis ya inútiles y los vigentes se pasaban del
# timeout. Cada petición toma un número de turno; si llega una más nueva, las
# anteriores (en espera o ya generando) se descartan.
_ticket_lock = threading.Lock()
_inference_lock = threading.Lock()
_latest_ticket = 0


def _new_ticket():
    global _latest_ticket
    with _ticket_lock:
        _latest_ticket += 1
        return _latest_ticket


def _stale_result():
    return {
        "concept": "",
        "complexity": "Low",
        "needs_assistance": False,
        "explanation": "",
        "stale": True
    }


def _is_english(value):
    lowered = f" {value.lower()} "
    return any(marker in lowered for marker in (" the ", " is ", " of ", " and ", " to "))


def _local_fallback(complexity):
    """Si el modelo responde en inglés pese a que se esperaba español, se
    reemplaza por un mensaje genérico en español en vez de dejarlo colar en el
    idioma equivocado."""
    if complexity == "Low":
        return {
            "concept": "Contenido sencillo",
            "explanation": "Esta imagen presenta una idea sencilla y fácil de seguir."
        }
    return {
        "concept": "Contenido visual",
        "explanation": "Esta imagen muestra información que puede requerir conocimientos previos para interpretarla."
    }


def _build_prompt(context, language):
    # El prompt va en el mismo idioma que se espera en la respuesta: con el
    # prompt en inglés, el modelo contestaba en inglés aunque la página fuera
    # en español. El pie de la figura da contexto del documento y fija el idioma.
    if language == "English":
        caption = f"Figure caption: {context}\n" if context else ""
        return (
            "You are an assistant that helps people understand visual content on a web page.\n"
            f"{caption}"
            "Reply with ONLY a one-line JSON, no markdown: "
            '{"concept": "3 to 5 words", "complexity": "Low, Medium or High", '
            '"explanation": "at most 25 words, in English, explaining the hardest term, concept '
            'or data pattern shown, without just describing the image"}. '
            'Use only what is visible in the image and the caption; do not invent data. '
            'If complexity is Low, "explanation" must be an empty string.'
        )

    caption = f"Pie de la figura: {context}\n" if context else ""
    return (
        "Eres un asistente que ayuda a entender contenido visual de una página web en español.\n"
        f"{caption}"
        "Responde SOLO con un JSON en una línea, sin markdown: "
        '{"concept": "3 a 5 palabras", "complexity": "Low, Medium o High", '
        '"explanation": "máximo 25 palabras, en español, que expliquen lo más difícil de la imagen '
        '(un término, concepto o patrón de los datos) sin limitarse a describirla"}. '
        'Usa solo lo que se ve en la imagen y el pie de figura; no inventes datos. '
        'Si la complejidad es Low, "explanation" debe ser una cadena vacía.'
    )


def _design_low_result():
    """Figura diseñada como Low: no se llama al modelo (igual que el texto
    fácil por legibilidad), respuesta instantánea y sin ayuda."""
    return {
        "concept": "",
        "complexity": "Low",
        "needs_assistance": False,
        "explanation": "",
        "difficulty_source": "diseño",
        "llm_complexity": None
    }


def apply_design_level(normalized, design_level):
    """Fija el nivel diseñado sobre el análisis del modelo y conserva el
    nivel que dijo el modelo en llm_complexity."""
    normalized["llm_complexity"] = normalized["complexity"]
    normalized["complexity"] = design_level
    normalized["needs_assistance"] = design_level != "Low"
    normalized["difficulty_source"] = "diseño"
    if normalized["needs_assistance"] and not normalized["explanation"]:
        # Red de seguridad: el prompt pide explicación vacía si el modelo juzga
        # Low. En la práctica Qwen la escribe igual (medido, ver README), pero
        # si llega vacía no se muestra un tooltip vacío.
        # No se cambió el prompt a "explicación obligatoria": se probó y alargó
        # la explicación de 19 a 46 palabras, hasta cortarse por tokens.
        normalized.update(_local_fallback(design_level))
    return normalized


def is_public_url(image_url):
    parsed = urlparse(image_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        print(f"[SSRF] Falla scheme/hostname: {image_url}")
        return False
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            print(f"[SSRF] IP resuelta: {ip} — privada:{ip.is_private} loopback:{ip.is_loopback}")
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                print(f"[SSRF] Bloqueada: {ip}")
                return False
        return True
    except (socket.gaierror, ValueError) as e:
        print(f"[SSRF] Error DNS: {e}")
        return False


def _clean_design_level(design_level):
    return design_level if design_level in VALID_DESIGN_LEVELS else None


def analyze_image(image_url, context="", design_level=None):
    design_level = _clean_design_level(design_level)
    if design_level == "Low":
        return _design_low_result()
    ticket = _new_ticket()
    print(f"\n===== ANALIZANDO IMAGEN (URL) =====")
    print(f"URL: {image_url}")

    if not isinstance(image_url, str) or len(image_url) > 2048 or not is_public_url(image_url):
        return {
            "concept": "Imagen no accesible",
            "complexity": "Low",
            "needs_assistance": False,
            "explanation": ""
        }

    try:
        http_response = requests.get(
            image_url,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10
        )
        print(f"[DEBUG] Imagen descargada: {len(http_response.content)} bytes")
        http_response.raise_for_status()
        image = Image.open(BytesIO(http_response.content)).convert("RGB")
    except Exception as e:
        print(f"Error descargando imagen: {e}")
        return {
            "concept": "Imagen no accesible",
            "complexity": "Low",
            "needs_assistance": False,
            "explanation": ""
        }

    return _analyze_pil_image(image, ticket, context, design_level)


def analyze_image_data(base64_data, context="", design_level=None):
    """Analiza una imagen generada en el cliente (gráficas/tablas renderizadas a PNG),
    recibida como base64 sin pasar por una descarga de red (sin riesgo de SSRF)."""
    design_level = _clean_design_level(design_level)
    if design_level == "Low":
        return _design_low_result()
    ticket = _new_ticket()
    print(f"\n===== ANALIZANDO IMAGEN (base64) =====")

    if not isinstance(base64_data, str) or not base64_data:
        return {
            "concept": "Imagen no accesible",
            "complexity": "Low",
            "needs_assistance": False,
            "explanation": ""
        }

    try:
        image_bytes = base64.b64decode(base64_data, validate=True)
        image = Image.open(BytesIO(image_bytes)).convert("RGB")
        print(f"[DEBUG] Imagen decodificada: {len(image_bytes)} bytes, {image.size}")
    except (binascii.Error, UnidentifiedImageError, ValueError, OSError) as e:
        print(f"Error decodificando imagen base64: {e}")
        return {
            "concept": "Imagen no accesible",
            "complexity": "Low",
            "needs_assistance": False,
            "explanation": ""
        }

    return _analyze_pil_image(image, ticket, context, design_level)


def _generate(prompt, image_b64, ticket):
    """Pide la respuesta a Ollama en streaming. Devuelve (texto, estado) con
    estado "ok", "stale" (llegó una petición más nueva) o "timeout". Al salir
    del bloque `with` se cierra la conexión y Ollama aborta la generación."""
    payload = {
        "model": VISION_MODEL,
        "prompt": prompt,
        "images": [image_b64],
        "stream": True,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0, "num_predict": MAX_NEW_TOKENS, "num_ctx": 2048}
    }
    # El reloj de GENERATION_TIMEOUT_S arranca con el primer fragmento de
    # respuesta: si el modelo estaba descargado de la GPU, cargarlo (hasta
    # ~30 s la primera vez) no debe contar como "generación lenta". Esa carga
    # está acotada por el timeout de lectura de 60 s de la conexión.
    deadline = None
    parts = []
    with requests.post(OLLAMA_GENERATE_URL, json=payload, stream=True, timeout=(5, 60)) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if ticket != _latest_ticket:
                return "".join(parts), "stale"
            if deadline is None:
                deadline = time.time() + GENERATION_TIMEOUT_S
            elif time.time() > deadline:
                return "".join(parts), "timeout"
            if not line:
                continue
            chunk = json.loads(line)
            parts.append(chunk.get("response", ""))
            if chunk.get("done"):
                break
    return "".join(parts), "ok"


def _analyze_pil_image(image, ticket, context="", design_level=None):
    context = (context or "").strip()[:CONTEXT_MAX_CHARS]
    language = detect_language(context) if context else "Spanish"

    if max(image.size) > MAX_IMAGE_SIDE:
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)
        print(f"[DEBUG] Imagen redimensionada a: {image.size}")

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    with _inference_lock:
        if ticket != _latest_ticket:
            print("[VISION] Petición descartada (ya hay una más nueva).")
            return _stale_result()

        try:
            started = time.time()
            model_output, status = _generate(_build_prompt(context, language), image_b64, ticket)

            if status == "stale":
                print("[VISION] Generación cortada (llegó una petición más nueva).")
                return _stale_result()
            if status == "timeout":
                raise TimeoutError("La generación del modelo de visión se pasó del tiempo")

            model_output = model_output.strip()
            print(f"[VISION] {time.time() - started:.2f}s ({language}): {model_output}")

            analysis = extract_json(model_output) or extract_partial_analysis(model_output)

            if not analysis:
                raise ValueError("No valid JSON in model output")

            normalized = normalize_analysis(analysis, "Imagen analizada")
            if language == "Spanish" and (
                _is_english(normalized["explanation"]) or _is_english(normalized["concept"])
            ):
                print("[LANGUAGE] El modelo respondió en inglés pese a la instrucción; se corrige a español.")
                normalized.update(_local_fallback(design_level or normalized["complexity"]))
            if design_level:
                normalized = apply_design_level(normalized, design_level)
            return normalized

        except Exception as e:
            print(f"Error analizando imagen: {e}")
            return {
                "concept": "Error de análisis",
                "complexity": design_level or "Medium",
                "needs_assistance": True,
                "explanation": "No se pudo analizar la imagen correctamente."
            }
