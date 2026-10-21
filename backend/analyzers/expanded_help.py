"""Segundo nivel de ayuda (explicación ampliada).

Se usa cuando la persona se vuelve a trabar en un párrafo DESPUÉS de haber
visto la primera ayuda (la definición de un término). Da:
  - 2 o 3 términos difíciles del párrafo con una definición breve (sin repetir
    el término que ya se definió en el primer nivel);
  - una frase que dice lo mismo que el párrafo en palabras simples.

Cambio de criterio respecto del primer nivel: allí NO se resume el texto
porque la persona ya lo leyó; aquí sí se reformula, porque ya mostró que no lo
entendió ni con la definición. Los términos se eligen como en el primer nivel
(text_analyzer.choose_terms): se descartan los que no aparecen en el párrafo,
los símbolos o fórmulas sueltos y los ya explicados en la página.
"""
import time

import requests

from analyzers.llm_utils import OLLAMA_KEEP_ALIVE, TEXT_MODEL, extract_json, trim_to_words
from analyzers.text_analyzer import OLLAMA_URL, TEXT_CHAR_LIMIT, TEXT_NUM_CTX, choose_terms

MAX_TERMS = 3
MAX_DEFINITION_WORDS = 25
MAX_SIMPLE_WORDS = 40

EXPANDED_SCHEMA = {
    "type": "object",
    "properties": {
        "terms": {
            "type": "array",
            # Sin tope, phi3 a veces enumeraba 4-5 términos largos, se acababan
            # los tokens y el JSON quedaba cortado (ayuda vacía).
            "maxItems": MAX_TERMS,
            "items": {
                "type": "object",
                "properties": {"term": {"type": "string"}, "definition": {"type": "string"}},
                "required": ["term", "definition"],
            },
        },
        "simple": {"type": "string"},
    },
    "required": ["terms", "simple"],
}


def build_expanded_prompt(text, section="", avoid_terms=()):
    context = f"Sección: {section}\n" if section else ""
    avoid_terms = [t for t in avoid_terms if t][:6]
    avoid = ("Ya se le explicó " + ", ".join(f'"{t}"' for t in avoid_terms) + ": NO lo vuelvas a definir.\n"
             if avoid_terms else "")
    return f"""Eres un asistente de lectura. La persona leyó este texto en español, recibió una primera ayuda y AÚN no lo entiende.

Devuelve SOLO este objeto JSON:
{{
"terms": [{{"term": "término difícil que aparece en el texto (1 a 3 palabras)", "definition": "máximo 20 palabras, en español, qué significa en palabras simples"}}],
"simple": "una sola oración de máximo 35 palabras que diga lo mismo que el texto, en palabras simples"
}}

Reglas:
- "terms": de 2 a 3 términos técnicos que aparezcan tal cual en el texto, del más al menos difícil.
- {avoid.strip() or "Elige los términos más difíciles."}
- "simple": explica la idea principal del texto como a alguien sin conocimientos previos. No agregues datos, cifras, nombres ni fechas que no estén en el texto. No uses analogías.
- Responde siempre en español.

{context}Texto: {text}"""


def expand_text(text, section="", already_defined="", defined_terms=()):
    """Devuelve {"terms": [...], "simple": str, "explanation": str,
    "discarded_terms": [...], "processing_time": s} o {"error": ...}."""
    truncated = text.strip()[:TEXT_CHAR_LIMIT]
    # Término del primer nivel + los ya explicados en la página: no se repiten.
    avoid_terms = [already_defined] + [t for t in defined_terms if t != already_defined]
    avoid_terms = [t.strip() for t in avoid_terms if t and t.strip()]
    started = time.time()
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": TEXT_MODEL,
                "prompt": build_expanded_prompt(truncated, section, avoid_terms),
                "stream": False,
                "format": EXPANDED_SCHEMA,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {"temperature": 0.1, "top_p": 0.9, "num_predict": 320,
                            # Mismo num_ctx que el primer nivel: si no, Ollama recarga phi3 (~6 s).
                            # Peor caso medido: 735 tokens (prompt + respuesta).
                            "num_ctx": TEXT_NUM_CTX},
            },
            timeout=30,
        )
        response.raise_for_status()
        data = extract_json(response.json()["response"].strip())
    except (requests.RequestException, ValueError, KeyError) as error:
        return {"error": str(error)}
    if not isinstance(data, dict) or not ("terms" in data or "simple" in data):
        return {"error": "respuesta sin JSON válido o incompleta"}

    # Misma elección que el primer nivel (text_analyzer.choose_terms): fuera
    # los que no están en el texto, símbolos o fórmulas ("CO₂") y los ya
    # explicados; primero el de la palabra con más sílabas.
    valid, discarded = choose_terms(data.get("terms") or [], truncated, avoid_terms, "silabas")
    terms = [{"term": t["term"][0].upper() + t["term"][1:],
              "definition": trim_to_words(t["definition"], MAX_DEFINITION_WORDS)}
             for t in valid[:MAX_TERMS]]

    simple = trim_to_words(str(data.get("simple", "")).strip(), MAX_SIMPLE_WORDS)
    lines = [f"{t['term']}: {t['definition']}" for t in terms]
    if simple:
        lines.append(f"En pocas palabras: {simple}")
    return {
        "terms": terms,
        "simple": simple,
        "explanation": "\n".join(lines),
        "discarded_terms": discarded,
        "processing_time": round(time.time() - started, 2),
    }
