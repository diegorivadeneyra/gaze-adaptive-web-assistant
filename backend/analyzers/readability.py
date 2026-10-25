"""Dificultad de lectura de un texto en español: índice de Szigriszt-Pazos
(1993) con la escala INFLESZ (Barrio-Cantalejo et al., 2008).

    INFLESZ = 206.835 - 62.3 * (sílabas / palabras) - (palabras / oraciones)

Determinista y explicable. Devuelve None en textos muy cortos (decide el modelo).
Copia en el navegador: frontend/js/readability.js (tests/test_readability.js).
"""
import re

WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ¿¡(\[])")

# Con menos palabras la fórmula es inestable (con 15, las frases de la página
# fácil caían al modelo y salían Medium).
MIN_WORDS = 8

# Escala INFLESZ: >= 55 normal o más fácil (Low), 40–55 algo difícil (Medium),
# < 40 muy difícil (High).
INFLESZ_LOW_MIN = 55
INFLESZ_MEDIUM_MIN = 40

_STRONG = set("aeoáéóàèò")
_WEAK = set("iuü")
_ACCENTED_WEAK = set("íú")
_VOWELS = _STRONG | _WEAK | _ACCENTED_WEAK


def count_syllables(word):
    """Cuenta sílabas de una palabra en español (aproximación por reglas:
    diptongos y triptongos forman una sílaba; los hiatos, dos)."""
    w = word.lower()
    w = re.sub(r"qu", "q", w)               # la u de que/qui no suena
    w = re.sub(r"gu([eiéí])", r"g\1", w)    # ni la de gue/gui (salvo ü)
    if w.endswith("y"):
        w = w[:-1] + "i"                    # y final funciona como vocal débil

    syllables = 0
    previous = None
    for char in w:
        if char not in _VOWELS:
            previous = None
            continue
        if previous is None:
            syllables += 1
        else:
            hiatus = (
                (previous in _STRONG and char in _STRONG)
                or previous in _ACCENTED_WEAK
                or char in _ACCENTED_WEAK
            )
            if hiatus:
                syllables += 1
        previous = char
    return max(syllables, 1)


def count_text_syllables(text):
    """Sílabas totales de un texto: base del tiempo de lectura esperado
    (decision_engine.READING_POLICY). Se usan sílabas y no palabras porque
    las palabras técnicas, más largas, tardan más aunque se entiendan."""
    return sum(count_syllables(w) for w in WORD_RE.findall(text))


def compute_readability(text):
    """Devuelve {"inflesz", "level", "words", "sentences", "label"} o None si
    el texto es demasiado corto para que la fórmula sea confiable."""
    words = WORD_RE.findall(text)
    if len(words) < MIN_WORDS:
        return None

    sentences = [s for s in SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]
    n_sentences = max(len(sentences), 1)
    syllables = sum(count_syllables(w) for w in words)

    inflesz = 206.835 - 62.3 * (syllables / len(words)) - (len(words) / n_sentences)

    if inflesz >= INFLESZ_LOW_MIN:
        level, label = "Low", "normal o más fácil"
    elif inflesz >= INFLESZ_MEDIUM_MIN:
        level, label = "Medium", "algo difícil"
    else:
        level, label = "High", "muy difícil"

    return {
        "inflesz": round(inflesz, 1),
        "level": level,
        "label": label,
        "words": len(words),
        "sentences": n_sentences,
    }
