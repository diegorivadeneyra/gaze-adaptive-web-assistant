import json
import re

import requests


VALID_COMPLEXITIES = {"Low", "Medium", "High"}

# Modelos locales en Ollama: gratis y sin internet una vez descargados.
OLLAMA_BASE_URL = "http://localhost:11434"
TEXT_MODEL = "phi3"
VISION_MODEL = "qwen2.5vl:3b"
# Modelos en memoria 30 min (por defecto 5 min y luego se recargan).
OLLAMA_KEEP_ALIVE = "30m"


def ensure_ollama_models(models):
    """Descarga los modelos que falten (solo la primera vez en cada
    computadora). Devuelve False si Ollama no está disponible."""
    try:
        tags = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5).json()
    except (requests.RequestException, ValueError):
        print("[OLLAMA] No se pudo conectar con Ollama en", OLLAMA_BASE_URL)
        print("[OLLAMA] Instálalo desde https://ollama.com/download y vuelve a correr.")
        return False

    installed = {m.get("name") for m in tags.get("models", [])}
    for model in models:
        full_name = model if ":" in model else f"{model}:latest"
        if full_name in installed:
            continue
        print(f"[OLLAMA] Descargando {model} (solo la primera vez)...")
        last_pct = -10
        try:
            with requests.post(
                f"{OLLAMA_BASE_URL}/api/pull",
                json={"model": model, "stream": True},
                stream=True,
                timeout=(5, 300)
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    info = json.loads(line)
                    if info.get("total") and info.get("completed"):
                        pct = int(info["completed"] * 100 / info["total"])
                        if pct >= last_pct + 10:
                            last_pct = pct
                            print(f"[OLLAMA]   {model}: {pct}%")
        except (requests.RequestException, ValueError) as e:
            print(f"[OLLAMA] No se pudo descargar {model}: {e}")
            return False
        print(f"[OLLAMA] {model} listo.")
    return True


def extract_json(text):
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
            if isinstance(value, dict):
                return value
        except json.JSONDecodeError:
            continue
    return None


def extract_partial_analysis(text):
    """Rescata un JSON cortado por falta de tokens: usa la explicación hasta
    su última oración completa."""
    concept = re.search(r'"concept"\s*:\s*"([^"]*)"', text)
    complexity = re.search(r'"complexity"\s*:\s*"([^"]*)"', text)
    explanation = re.search(r'"explanation"\s*:\s*"(.*)', text, re.DOTALL)
    if not explanation:
        return None

    partial = explanation.group(1).split('"')[0].strip()
    last_end = max(partial.rfind("."), partial.rfind("!"), partial.rfind("?"))
    if last_end > 20:
        partial = partial[:last_end + 1]
    if len(partial) < 20:
        return None

    return {
        "concept": concept.group(1) if concept else "",
        "complexity": complexity.group(1) if complexity else "Medium",
        "explanation": partial
    }


def clean_explanation(value):
    """Une en un párrafo las explicaciones que phi3 devuelve como lista o
    numeradas ("1) ... 2) ..."); los decimales como 2.31 no se tocan."""
    if isinstance(value, (list, tuple)):
        value = " ".join(str(item) for item in value)
    text = str(value or "")
    text = re.sub(r"(?<!\S)\(?[1-9][.)]\s+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


# phi3 ignora el tope de palabras del prompt (pedirle 40 daba hasta 65–90):
# el límite se aplica aquí.
MAX_EXPLANATION_WORDS = 55


def trim_to_words(text, max_words=MAX_EXPLANATION_WORDS):
    """Recorta en el último límite de oración dentro de max_words palabras; si
    no hay un punto razonable, corta en max_words y añade "…"."""
    words = text.split()
    if len(words) <= max_words:
        return text
    head = " ".join(words[:max_words])
    last_end = max(head.rfind("."), head.rfind("!"), head.rfind("?"))
    if last_end >= len(head) * 0.4:
        return head[:last_end + 1]
    return head.rstrip(",;: ") + "…"


def normalize_analysis(value, default_concept):
    if not isinstance(value, dict):
        raise ValueError("LLM response must be a JSON object")

    complexity = value.get("complexity", "Medium")
    if isinstance(complexity, str):
        complexity = complexity.strip().capitalize()
    if complexity not in VALID_COMPLEXITIES:
        complexity = "Medium"

    concept = value.get("concept", default_concept)
    explanation = value.get("explanation", "")

    return {
        "concept": str(concept).strip()[:200],
        "complexity": complexity,
        # Se deriva del nivel: el modelo a veces se contradecía.
        "needs_assistance": complexity != "Low",
        "explanation": trim_to_words(clean_explanation(explanation))
    }