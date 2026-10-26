import re
import threading
import unicodedata

import requests
from analyzers.llm_utils import (
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    TEXT_MODEL,
    extract_json,
    extract_partial_analysis,
    normalize_analysis,
)
from analyzers.readability import compute_readability, count_syllables

OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/generate"

# Caracteres del texto que se envían (con 400 se cortaba el final técnico).
TEXT_CHAR_LIMIT = 900

# Ventana de contexto compartida con expanded_help.py: si cambia, Ollama
# recarga phi3 (~6 s).
TEXT_NUM_CTX = 1024

# Límite de espera de phi3. Con GPU de 6 GB los dos modelos no caben juntos y
# recargar phi3 tras una gráfica tomó ~8 s (laptop RTX 3050, medido 2026-10-25).
TEXT_TIMEOUT_S = 25

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "concept": {"type": "string"},
        "complexity": {"type": "string", "enum": ["Low", "Medium", "High"]},
        "explanation": {"type": "string"},
    },
    "required": ["concept", "complexity", "explanation"],
}

# Elección del término a definir. "modelo": el modelo elige uno. "candidatos":
# propone 3 y se toma el primero que pasa los filtros. "silabas": el de más
# sílabas entre los que pasan (elegido con evaluation/ab_terminos.py).
# Filtros: está en el texto, no es solo un símbolo ("CO₂") y no se explicó ya
# en la página.
TERM_SELECTION = "silabas"
TERM_SELECTION_MODES = ("modelo", "candidatos", "silabas")
MAX_CANDIDATES = 3

CANDIDATES_SCHEMA = {
    "type": "object",
    "properties": {
        "terms": {
            "type": "array",
            "maxItems": MAX_CANDIDATES,
            "items": {
                "type": "object",
                "properties": {"term": {"type": "string"}, "definition": {"type": "string"}},
                "required": ["term", "definition"],
            },
        },
        "complexity": {"type": "string", "enum": ["Low", "Medium", "High"]},
    },
    "required": ["terms", "complexity"],
}


def detect_language(text):
    # Sin marcadores claros (tablas de números y siglas) se asume español.
    lowered = f" {text.lower()} "
    spanish_markers = (
        " el ", " la ", " los ", " las ", " que ", " de ", " y ",
        " una ", " para ", " con ", "ción", "ñ", "¿", "¡",
        " energía", " sistema", " ecuación", " texto", " usuario"
    )
    english_markers = (" the ", " is ", " of ", " and ", " this ", " are ", " with ")
    spanish_score = sum(marker in lowered for marker in spanish_markers)
    if spanish_score >= 1:
        return "Spanish"
    english_score = sum(marker in lowered for marker in english_markers)
    return "English" if english_score >= 1 else "Spanish"


def _matches_language(value, language):
    if not value:
        return True
    # Se busca un marcador del OTRO idioma: frases cortas válidas ("Cambio
    # climático") no tienen marcadores del propio.
    lowered = f" {value.lower()} "
    spanish_markers = (" el ", " la ", " que ", " de ", " y ", " para ", " una ", " es ", " los ", " las ")
    # Sin " a ": también es preposición en español.
    english_markers = (" the ", " is ", " of ", " and ", " this ", " are ", " with ", " you ")
    other_markers = english_markers if language == "Spanish" else spanish_markers
    return not any(marker in lowered for marker in other_markers)


def _local_language_fallback(language, complexity):
    if language == "Spanish":
        return {
            "concept": "Contenido académico" if complexity != "Low" else "Contenido sencillo",
            "explanation": (
                "Este contenido usa conceptos que pueden requerir conocimientos previos."
                if complexity != "Low"
                else "Este contenido presenta una idea sencilla y fácil de seguir."
            )
        }
    return {
        "concept": "Academic content" if complexity != "Low" else "Simple content",
        "explanation": (
            "This content uses concepts that may require some previous knowledge."
            if complexity != "Low"
            else "This content presents a simple idea that is easy to follow."
        )
    }


_COPULAS = {"es", "son", "se", "significa", "consiste", "indica", "describe", "mide", "representa", "is", "are"}


def _with_term(concept, explanation):
    """Antepone el término a la definición: "Término: es un …"."""
    concept = concept.strip(" .:;")
    if not concept or not explanation:
        return explanation
    head = concept[0].upper() + concept[1:]
    first_word = explanation.split(" ", 1)[0].lower().strip(",.;:")
    body = explanation[0].lower() + explanation[1:] if first_word in _COPULAS else explanation
    return f"{head}: {body}"


def _context_block(language, page_context):
    """Título y sección como contexto, no como tema a definir."""
    page_context = page_context or {}
    title, section = page_context.get("title"), page_context.get("section")
    if not title and not section:
        return ""
    if language == "Spanish":
        lines = ["Contexto, solo para entender el texto (NO lo expliques salvo que el término difícil del texto esté ahí):"]
        if title:
            lines.append(f"- Título de la página: {title}")
        if section:
            lines.append(f"- Sección: {section}")
    else:
        lines = ["Context, only to understand the text (do NOT explain it unless the hard term of the text is there):"]
        if title:
            lines.append(f"- Page title: {title}")
        if section:
            lines.append(f"- Section: {section}")
    return "\n".join(lines) + "\n\n"


def build_prompt(language, truncated, page_context=None):
    context = _context_block(language, page_context)
    # La persona ya leyó el texto: se define el término difícil, sin recapitular.
    if language == "Spanish":
        return f"""Eres un asistente de lectura. La persona YA LEYÓ este texto (está en español) y no lo terminó de entender, así que NO se lo repitas.

Devuelve SOLO este objeto JSON:
{{
"concept": "el término técnico más difícil que aparece en el texto (1 a 3 palabras, no el tema general)",
"complexity": "Low, Medium o High",
"explanation": "máximo 35 palabras, en español, un solo párrafo"
}}

Reglas:
- Responde siempre en español.
- complexity: High = términos técnicos o especializados; Medium = requiere conocimientos previos; Low = simple y claro.
- explanation: explica ESE término: qué significa en palabras simples y, si ayuda, para qué sirve o por qué importa. NO repitas, NO resumas ni parafrasees lo que el texto ya dice. Puedes explicar conceptos generales, pero NO inventes datos, cifras, nombres ni fechas. NO uses analogías ni comparaciones. NO empieces con "Imagina".

{context}Texto: {truncated}"""
    else:
        return f"""You are a reading assistant. The person ALREADY READ this text (it is in English) and did not fully understand it, so do NOT repeat it to them.

Return ONLY this JSON object:
{{
"concept": "the hardest technical term that appears in the text (1 to 3 words, not the general topic)",
"complexity": "Low, Medium or High",
"explanation": "at most 35 words, in English, a single paragraph"
}}

Rules:
- Always answer in English.
- complexity: High = technical or specialized terms; Medium = requires prior knowledge; Low = simple and clear.
- explanation: explain THAT term: what it means in plain words and, if useful, what it is for or why it matters. Do NOT repeat, summarize or paraphrase what the text already says. You may explain general concepts, but do NOT invent data, figures, names or dates. Do NOT use analogies or comparisons. Do NOT start with "Imagine".

{context}Text: {truncated}"""


def build_candidates_prompt(truncated, page_context=None):
    context = _context_block("Spanish", page_context)
    return f"""Eres un asistente de lectura. La persona YA LEYÓ este texto (está en español) y no lo terminó de entender, así que NO se lo repitas.

Devuelve SOLO este objeto JSON:
{{
"terms": [{{"term": "término técnico que aparece tal cual en el texto (1 a 3 palabras)", "definition": "máximo 35 palabras, en español, un solo párrafo"}}],
"complexity": "Low, Medium o High"
}}

Reglas:
- Responde siempre en español.
- terms: de 1 a 3 términos, del más al menos difícil para alguien que no conoce el tema. NO elijas palabras de uso común, el tema general del texto ni símbolos o fórmulas sueltos (como CO₂ o pH).
- complexity: High = términos técnicos o especializados; Medium = requiere conocimientos previos; Low = simple y claro.
- definition: explica ESE término: qué significa en palabras simples y, si ayuda, para qué sirve o por qué importa. NO repitas, NO resumas ni parafrasees lo que el texto ya dice. Puedes explicar conceptos generales, pero NO inventes datos, cifras, nombres ni fechas. NO uses analogías ni comparaciones. NO empieces con "Imagina".

{context}Texto: {truncated}"""


def is_symbol_term(term):
    """Solo símbolos, fórmulas o siglas de menos de 4 letras ("CO₂", "pH",
    "W m⁻²"): ninguna palabra de 4+ letras."""
    return not any(len(word) >= 4 for word in _normalize_words(term))


def _term_stems(term):
    return {word[:max(4, len(word) - 2)] for word in _normalize_words(term) if len(word) >= 4}


def same_term(a, b):
    """Mismo término o uno contenido en el otro ("forzamiento radiativo
    efectivo" ~ "forzamiento radiativo efectivo antropogénico")."""
    sa, sb = _term_stems(a), _term_stems(b)
    if not sa or not sb:
        return False
    small, big = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    # Tolerando la terminación: "emision" ~ "emisi" (emisiones / emisión).
    return all(any(x.startswith(y) or y.startswith(x) for y in big) for x in small)


def term_syllables(term):
    """Sílabas de la palabra más larga del término (proxy de rareza)."""
    words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", term)
    return max((count_syllables(w) for w in words), default=0)


def choose_terms(candidates, text, defined_terms=(), mode="candidatos"):
    """Filtra y ordena candidatos [{"term", "definition"}].
    Devuelve (válidos en orden de preferencia, descartados con motivo)."""
    valid, discarded = [], []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        term = str(item.get("term", "")).strip(" .:;")
        definition = str(item.get("definition", "")).strip()
        if not term or not definition:
            continue
        reason = None
        if is_symbol_term(term):
            reason = "simbolo"
        elif not concept_in_text(term, text):
            reason = "fuera_del_texto"
        elif any(same_term(term, d) for d in defined_terms):
            reason = "ya_definido_en_la_pagina"
        elif any(same_term(term, v["term"]) for v in valid):
            reason = "duplicado"
        if reason:
            discarded.append({"term": term, "reason": reason})
        else:
            valid.append({"term": term, "definition": definition})
    if mode == "silabas":
        valid.sort(key=lambda v: -term_syllables(v["term"]))   # estable: empata en el orden del modelo
    return valid, discarded


def _normalize_words(value):
    value = unicodedata.normalize("NFKD", value.lower())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.findall(r"[a-z0-9]+", value)


def concept_in_text(concept, text):
    """¿El término aparece en el texto? Cada palabra de 4+ letras, sin tildes
    y tolerando la terminación ("promedios" ~ "promedio"). Evita definir
    términos inventados por phi3."""
    text_words = _normalize_words(text)
    joined = " " + " ".join(text_words)
    for word in _normalize_words(concept):
        if len(word) < 4:
            continue
        stem = word[:max(4, len(word) - 2)]
        if f" {stem}" not in joined:
            return False
    return True


def _readability_fields(readability):
    if not readability:
        return {}
    return {"inflesz": readability["inflesz"], "inflesz_label": readability["label"]}


def _fallback_result(language, readability):
    """Si el modelo falla: el nivel de legibilidad si existe; si no, Medium."""
    level = readability["level"] if readability else "Medium"
    fallback = _local_language_fallback(language, level)
    return {
        "concept": fallback["concept"],
        "complexity": level,
        "needs_assistance": level != "Low",
        "explanation": fallback["explanation"],
        "difficulty_source": "legibilidad" if readability else "modelo",
        **_readability_fields(readability)
    }


_reload_lock = threading.Lock()


def reload_text_model():
    """Vuelve a cargar phi3 en la GPU (con un prompt vacío Ollama solo lo carga).
    Se llama en segundo plano tras usar el modelo de visión: si los dos no caben,
    así la siguiente ayuda de texto no paga la recarga."""
    if not _reload_lock.acquire(blocking=False):
        return
    try:
        requests.post(OLLAMA_URL, json={"model": TEXT_MODEL, "prompt": "", "stream": False,
                                        "keep_alive": OLLAMA_KEEP_ALIVE,
                                        "options": {"num_ctx": TEXT_NUM_CTX}}, timeout=60)
    except requests.RequestException:
        pass
    finally:
        _reload_lock.release()


def analyze_text(text, use_readability=True, page_context=None, defined_terms=(), term_selection=None):
    if len(text.strip()) < 20:
        return {
            "concept": "Contenido breve",
            "complexity": "Low",
            "needs_assistance": False,
            "explanation": ""
        }

    # Nivel: INFLESZ en texto corrido; el modelo en tablas y textos cortos.
    readability = compute_readability(text) if use_readability else None
    extra = _readability_fields(readability)

    # Low: sin ayuda, no se llama al modelo.
    if readability and readability["level"] == "Low":
        return {
            "concept": "Contenido sencillo",
            "complexity": "Low",
            "needs_assistance": False,
            "explanation": "",
            "difficulty_source": "legibilidad",
            **extra
        }

    truncated = text.strip()[:TEXT_CHAR_LIMIT]
    language = detect_language(truncated)

    mode = term_selection if term_selection in TERM_SELECTION_MODES else TERM_SELECTION
    # Solo texto corrido en español; tablas e inglés siguen con un término.
    use_candidates = mode != "modelo" and use_readability and language == "Spanish"
    prompt = (build_candidates_prompt(truncated, page_context) if use_candidates
              else build_prompt(language, truncated, page_context))

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": TEXT_MODEL,
                "prompt": prompt,
                "stream": False,
                # Esquema estricto: con "json" a secas phi3 deformaba las claves.
                "format": CANDIDATES_SCHEMA if use_candidates else ANALYSIS_SCHEMA,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9,
                    # Con 120 el JSON se cortaba; los candidatos traen 3 definiciones.
                    "num_predict": 320 if use_candidates else 200,
                    "num_ctx": TEXT_NUM_CTX
                }
            },
            timeout=TEXT_TIMEOUT_S
        )
        response.raise_for_status()
        response_text = response.json()["response"].strip()

        analysis = extract_json(response_text)

        term_info = None
        if use_candidates:
            if not isinstance(analysis, dict) or "terms" not in analysis:
                raise ValueError("Respuesta de candidatos sin JSON válido")
            raw = analysis.get("terms") or []
            valid, discarded = choose_terms(raw, truncated, defined_terms, mode)
            term_info = {
                "term_selection": mode,
                "term_candidates": [str(t.get("term", "")) for t in raw if isinstance(t, dict)],
                "term_discarded": discarded,
            }
            chosen = valid[0] if valid else {"term": "", "definition": ""}
            analysis = {"concept": chosen["term"], "complexity": analysis.get("complexity", "Medium"),
                        "explanation": chosen["definition"]}

        if not analysis:
            # JSON cortado: se rescata hasta la última oración completa.
            analysis = extract_partial_analysis(response_text)
            if analysis:
                print("[JSON] Respuesta de phi3 cortada; se recuperó parcialmente.")

        if not analysis:
            print(f"[JSON] No se pudo parsear la respuesta de phi3: {response_text!r}")
            raise ValueError("No valid JSON found in response")

        normalized = normalize_analysis(analysis, "Contenido analizado")

        # Manda la legibilidad; lo que dijo el modelo queda en llm_complexity.
        normalized["llm_complexity"] = normalized["complexity"]
        if readability:
            normalized["complexity"] = readability["level"]
            normalized["needs_assistance"] = readability["level"] != "Low"
        normalized["difficulty_source"] = "legibilidad" if readability else "modelo"
        normalized.update(extra)
        if term_info:
            normalized.update(term_info)

        if (
            not _matches_language(normalized["concept"], language)
            or not _matches_language(normalized["explanation"], language)
        ):
            normalized.update(_local_language_fallback(language, normalized["complexity"]))
        elif term_info and not normalized["concept"]:
            # Ningún candidato pasó los filtros: sin ayuda.
            normalized["needs_assistance"] = False
            normalized["help_blocked"] = "sin_termino_valido"
        elif not concept_in_text(normalized["concept"], truncated):
            # Término fuera del texto (suele ser inventado): sin ayuda.
            print(f"[AYUDA] Bloqueada: '{normalized['concept']}' no aparece en el texto.")
            normalized["needs_assistance"] = False
            normalized["help_blocked"] = "termino_fuera_del_texto"
        else:
            normalized["explanation"] = _with_term(normalized["concept"], normalized["explanation"])
        return normalized

    except requests.exceptions.Timeout:
        return _fallback_result(language, readability)
    except Exception as e:
        print(f"Error en analyze_text: {e}")
        return _fallback_result(language, readability)