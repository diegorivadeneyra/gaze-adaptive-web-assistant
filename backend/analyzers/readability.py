"""Medida objetiva de dificultad de lectura para texto en español.

Se usa el índice de legibilidad de Szigriszt-Pazos (1993) con la escala
INFLESZ (Barrio-Cantalejo et al., 2008), que es una adaptación al español de
la fórmula de Flesch:

    INFLESZ = 206.835 - 62.3 * (sílabas / palabras) - (palabras / oraciones)

Es determinista (mismo texto, mismo resultado), gratis y explicable, a
diferencia de pedirle el nivel a un modelo de lenguaje. No aplica a tablas,
gráficas ni imágenes, ni a textos muy cortos: en esos casos devuelve None y
el sistema recurre al juicio del modelo.
"""
import re

WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ¿¡(\[])")

# Con menos palabras la fórmula es inestable, así que se deja al modelo. Se
# empezó con 15, pero entonces las frases cortas de la página fácil (12-14
# palabras) caían al juicio del modelo, que las calificaba "Medium" y daba
# ayuda donde no corresponde; con 8, 8 de esas 9 frases salen "Low" (la novena
# es 49.5, en el borde de "Medium"), que es lo esperado.
MIN_WORDS = 8

# Cortes de la escala INFLESZ agrupados en los tres niveles del sistema:
#   >= 55  "normal" o más fácil  -> Low    (no se ofrece ayuda)
#   40-55  "algo difícil"        -> Medium
#   < 40   "muy difícil"         -> High
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
