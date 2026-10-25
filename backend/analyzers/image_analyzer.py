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
CHART_TEXT_MAX_CHARS = 600

# Nivel diseñado de la figura (data-design-level en el HTML): reemplaza al del
# modelo, que cambiaba con el prompt. El del modelo queda en llm_complexity.
VALID_DESIGN_LEVELS = {"Low", "Medium", "High"}

# Una inferencia a la vez y "el último gana": cada petición toma un turno y las
# anteriores (en espera o generando) se descartan.
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
    """Mensaje genérico en español si el modelo respondió en otro idioma."""
    if complexity == "Low":
        return {
            "concept": "Contenido sencillo",
            "explanation": "Esta imagen presenta una idea sencilla y fácil de seguir."
        }
    return {
        "concept": "Contenido visual",
        "explanation": "Esta imagen muestra información que puede requerir conocimientos previos para interpretarla."
    }


def _page_line(language, page_context):
    page_context = page_context or {}
    parts = []
    if page_context.get("title"):
        parts.append(("Page title: " if language == "English" else "Título de la página: ") + page_context["title"])
    if page_context.get("section"):
        parts.append(("Section: " if language == "English" else "Sección: ") + page_context["section"])
    return (". ".join(parts) + "\n") if parts else ""


def _build_prompt(context, language, chart_text="", page_context=None):
    page = _page_line(language, page_context)
    # Prompt en el idioma de la respuesta. En gráficas se pasan sus textos
    # (ejes, valores) y se pide explicar qué mide, no describir la línea.
    if language == "English":
        caption = f"Figure caption: {context}\n" if context else ""
        texts = (f"Text written in the chart, in document order (title, axes, values, labels): {chart_text}\n"
                 "Use these exact values instead of reading them from the image.\n") if chart_text else ""
        explanation = (
            "at most 25 words, in English, explaining what the chart measures (the quantity, unit or "
            "reference) and its main pattern, without just describing it"
        ) if chart_text else (
            "at most 25 words, in English, explaining the hardest term, concept "
            "or data pattern shown, without just describing the image"
        )
        return (
            "You are an assistant that helps people understand visual content on a web page.\n"
            f"{page}{caption}{texts}"
            "Reply with ONLY a one-line JSON, no markdown: "
            '{"concept": "3 to 5 words", "complexity": "Low, Medium or High", '
            f'"explanation": "{explanation}"}}. '
            'Use only what is visible in the image and the caption; do not invent data. '
            'If complexity is Low, "explanation" must be an empty string.'
        )

    caption = f"Pie de la figura: {context}\n" if context else ""
    texts = (f"Textos escritos en la gráfica, en el orden del documento (título, ejes, valores, etiquetas): {chart_text}\n"
             "Usa estos valores exactos en lugar de leerlos de la imagen.\n") if chart_text else ""
    explanation = (
        "máximo 25 palabras, en español, que expliquen qué mide la gráfica (la magnitud, la unidad o la "
        "referencia) y su patrón principal, sin limitarse a describirla"
    ) if chart_text else (
        "máximo 25 palabras, en español, que expliquen lo más difícil de la imagen "
        "(un término, concepto o patrón de los datos) sin limitarse a describirla"
    )
    return (
        "Eres un asistente que ayuda a entender contenido visual de una página web en español.\n"
        f"{page}{caption}{texts}"
        "Responde SOLO con un JSON en una línea, sin markdown: "
        '{"concept": "3 a 5 palabras", "complexity": "Low, Medium o High", '
        f'"explanation": "{explanation}"}}. '
        'Usa solo lo que se ve en la imagen y el pie de figura; no inventes datos. '
        'Si la complejidad es Low, "explanation" debe ser una cadena vacía.'
    )


def _design_low_result():
    """Figura diseñada como Low: sin ayuda, no se llama al modelo."""
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
        # Si el modelo dejó la explicación vacía, mensaje genérico (no tooltip vacío).
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
            if ip.is_private or ip.is_loopback or ip.is_link_local:
                print(f"[SSRF] Bloqueada: {ip}")
                return False
        return True
    except (socket.gaierror, ValueError) as e:
        print(f"[SSRF] Error DNS: {e}")
        return False


def _clean_design_level(design_level):
    return design_level if design_level in VALID_DESIGN_LEVELS else None


def analyze_image(image_url, context="", design_level=None, page_context=None):
    design_level = _clean_design_level(design_level)
    if design_level == "Low":
        return _design_low_result()
    ticket = _new_ticket()

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

    return _analyze_pil_image(image, ticket, context, design_level, page_context=page_context)


def analyze_image_data(base64_data, context="", design_level=None, chart_text="", page_context=None):
    """Imagen generada en el navegador (gráfica en PNG, base64): sin descarga."""
    design_level = _clean_design_level(design_level)
    if design_level == "Low":
        return _design_low_result()
    ticket = _new_ticket()

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
    except (binascii.Error, UnidentifiedImageError, ValueError, OSError) as e:
        print(f"Error decodificando imagen base64: {e}")
        return {
            "concept": "Imagen no accesible",
            "complexity": "Low",
            "needs_assistance": False,
            "explanation": ""
        }

    return _analyze_pil_image(image, ticket, context, design_level, chart_text, page_context)


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
    # El límite de generación corre desde el primer fragmento: la carga del
    # modelo (hasta ~30 s) no cuenta; la acota el timeout de 60 s.
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


def _analyze_pil_image(image, ticket, context="", design_level=None, chart_text="", page_context=None):
    context = (context or "").strip()[:CONTEXT_MAX_CHARS]
    chart_text = (chart_text or "").strip()[:CHART_TEXT_MAX_CHARS]
    language = detect_language(context) if context else "Spanish"

    if max(image.size) > MAX_IMAGE_SIDE:
        image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE), Image.LANCZOS)

    buffer = BytesIO()
    image.save(buffer, format="PNG")
    image_b64 = base64.b64encode(buffer.getvalue()).decode("ascii")

    with _inference_lock:
        if ticket != _latest_ticket:
            print("[VISION] Petición descartada (ya hay una más nueva).")
            return _stale_result()

        try:
            started = time.time()
            model_output, status = _generate(_build_prompt(context, language, chart_text, page_context), image_b64, ticket)

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
