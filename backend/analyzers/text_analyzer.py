import requests
from analyzers.llm_utils import (
    OLLAMA_BASE_URL,
    OLLAMA_KEEP_ALIVE,
    TEXT_MODEL,
    extract_json,
    extract_partial_analysis,
    normalize_analysis,
)
from analyzers.readability import compute_readability

OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/generate"

# Límite de caracteres del texto a analizar. Con 400 se cortaba lo técnico al
# final de párrafos de ~450 caracteres; 900 no cambia la velocidad medida
# (~3.1 s vs ~3.2 s) y cabe de sobra en num_ctx=1024 junto al prompt.
TEXT_CHAR_LIMIT = 900

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "concept": {"type": "string"},
        "complexity": {"type": "string", "enum": ["Low", "Medium", "High"]},
        "explanation": {"type": "string"},
    },
    "required": ["concept", "complexity", "explanation"],
}


def detect_language(text):
    # Contenido corto/denso (sobre todo tablas extraídas como texto plano,
    # ej. "CO2-eq 2.31 0.17 <0.001") puede no tener NINGÚN marcador de
    # español ni de inglés — son solo números y siglas. Como esta app es
    # 100% contenido en español, se asume español por defecto cuando no hay
    # evidencia clara de inglés, en vez de caer a inglés por defecto (que
    # era lo que hacía que el modelo respondiera en inglés para tablas).
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
    # "concept" son solo 3 palabras y muchas frases nominales válidas en español
    # (p.ej. "Cambio climático") no contienen ningún artículo/preposición de la
    # lista, así que exigir un marcador del idioma esperado descartaba respuestas
    # correctas. En cambio, se busca un marcador claro del OTRO idioma: una señal
    # mucho más confiable de que el modelo sí respondió en el idioma equivocado.
    lowered = f" {value.lower()} "
    spanish_markers = (" el ", " la ", " que ", " de ", " y ", " para ", " una ", " es ", " los ", " las ")
    # " a "/" an " se excluyen a propósito: "a" es una preposición española muy
    # común ("ayuda a entender"), así que como marcador de inglés daba muchos
    # falsos positivos sobre explicaciones en español correctas.
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
    """La explicación ya no recapitula el texto, así que suele empezar con "Es
    un método…" o "Son errores…": sin el término, el usuario no sabría a qué se
    refiere. Se antepone el término como encabezado: "Término: es un …"."""
    concept = concept.strip(" .:;")
    if not concept or not explanation:
        return explanation
    head = concept[0].upper() + concept[1:]
    first_word = explanation.split(" ", 1)[0].lower().strip(",.;:")
    body = explanation[0].lower() + explanation[1:] if first_word in _COPULAS else explanation
    return f"{head}: {body}"


def build_prompt(language, truncated):
    # La persona ya leyó el texto: la ayuda no debe recapitularlo (medido: la
    # versión anterior, que pedía "qué dice el texto con eso", copiaba ~11 %
    # de sus trigramas; esta ~3 %). "concept" pasa a ser el término técnico
    # concreto que se explica: obliga al modelo a elegir uno antes de definirlo
    # (si no, solía elegir el tema general en vez del término difícil).
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

Texto: {truncated}"""
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

Text: {truncated}"""


def _readability_fields(readability):
    if not readability:
        return {}
    return {"inflesz": readability["inflesz"], "inflesz_label": readability["label"]}


def _fallback_result(language, readability):
    """Si el modelo falla (timeout, JSON inválido...), se conserva el nivel
    medido por legibilidad cuando existe; si no, se asume Medium."""
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


def analyze_text(text, use_readability=True):
    if len(text.strip()) < 20:
        return {
            "concept": "Contenido breve",
            "complexity": "Low",
            "needs_assistance": False,
            "explanation": ""
        }

    # Nivel de dificultad: para texto corrido en español se usa la legibilidad
    # (INFLESZ), una medida objetiva y determinista. Para tablas, textos muy
    # cortos o cuando no hay medida, se usa el juicio del modelo.
    readability = compute_readability(text) if use_readability else None
    extra = _readability_fields(readability)

    # "Normal o más fácil" según INFLESZ: no se ofrece ayuda, así que ni
    # siquiera se llama al modelo (respuesta instantánea y sin carga de GPU).
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

    prompt = build_prompt(language, truncated)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": TEXT_MODEL,
                "prompt": prompt,
                "stream": False,
                # Esquema estricto: fija las claves y los tipos. Con "json" a
                # secas phi3 a veces deformaba el nombre de la clave
                # ("explande", "explanranza"), la explicación quedaba vacía y
                # no salía tooltip; sin formato repetía el prompt o encadenaba
                # varios objetos tras la respuesta.
                "format": ANALYSIS_SCHEMA,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {
                    "temperature": 0.1,
                    "top_p": 0.9,
                    # 120 era muy justo: si phi3 se explaya un poco (pasa
                    # seguido con modelos chicos pese a pedirle brevedad), la
                    # respuesta se cortaba ANTES de cerrar el JSON, el parseo
                    # fallaba, y eso también disparaba el mensaje genérico de
                    # "conocimientos previos" — en texto normal, no solo tablas.
                    "num_predict": 200,
                    "num_ctx": 1024
                }
            },
            timeout=15
        )
        response.raise_for_status()
        response_text = response.json()["response"].strip()

        analysis = extract_json(response_text)

        if not analysis:
            # Suele ser un JSON cortado por num_predict (el modelo se explayó):
            # se rescata la explicación hasta la última oración completa.
            analysis = extract_partial_analysis(response_text)
            if analysis:
                print("[JSON] Respuesta de phi3 cortada; se recuperó parcialmente.")

        if not analysis:
            print(f"[JSON] No se pudo parsear la respuesta de phi3: {response_text!r}")
            raise ValueError("No valid JSON found in response")

        normalized = normalize_analysis(analysis, "Contenido analizado")

        # El nivel final lo fija la legibilidad si existe; la complejidad que
        # dijo el modelo se conserva aparte (llm_complexity) para poder medir
        # cuánto coinciden ambas.
        normalized["llm_complexity"] = normalized["complexity"]
        if readability:
            normalized["complexity"] = readability["level"]
            normalized["needs_assistance"] = readability["level"] != "Low"
        normalized["difficulty_source"] = "legibilidad" if readability else "modelo"
        normalized.update(extra)

        if (
            not _matches_language(normalized["concept"], language)
            or not _matches_language(normalized["explanation"], language)
        ):
            normalized.update(_local_language_fallback(language, normalized["complexity"]))
        else:
            normalized["explanation"] = _with_term(normalized["concept"], normalized["explanation"])
        return normalized

    except requests.exceptions.Timeout:
        return _fallback_result(language, readability)
    except Exception as e:
        print(f"Error en analyze_text: {e}")
        return _fallback_result(language, readability)